"""Persistent incremental polling; one scheduler across application instances."""
import logging
import os
import threading
from datetime import datetime, timedelta, timezone

import psycopg
from fastapi import APIRouter, Depends, HTTPException

from booking_storage import PROPERTY_ID, authorize, connect
from booking_details import prepare_details, retry_delay, launch_worker as launch_details
from reconciliation import update_summaries

INTERVAL = 300
_stop = threading.Event()
_guard = threading.Lock()
_thread = None
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/storage/auto", tags=["Automatic synchronization"], dependencies=[Depends(authorize)])


def prepare_auto(conn):
    conn.execute("SELECT pg_advisory_xact_lock(4950, 5)")
    conn.execute("""CREATE TABLE IF NOT EXISTS tl_auto_sync (
        property_id text PRIMARY KEY, enabled boolean NOT NULL DEFAULT true,
        next_run_at timestamptz NOT NULL DEFAULT now(),
        last_success_at timestamptz, last_error text,
        failures integer NOT NULL DEFAULT 0,
        draining boolean NOT NULL DEFAULT false,
        updated_at timestamptz NOT NULL DEFAULT now())""")
    conn.execute("INSERT INTO tl_auto_sync (property_id) VALUES (%s) ON CONFLICT DO NOTHING", (PROPERTY_ID,))


def wake_details(conn):
    # Respect a manual pause, a failure requiring inspection and existing Retry-After.
    # The detail worker already resumes running jobs and processes only stale hashes.
    with conn.transaction():
        prepare_details(conn)
        conn.execute("""UPDATE tl_detail_job SET state = 'running', updated_at = now()
            WHERE property_id = %s AND state = 'completed'""", (PROPERTY_ID,))
    launch_details()


def poll_once(conn, now=None):
    """Caller holds session lock 4950,4; conn must be autocommit."""
    now = now or datetime.now(timezone.utc)
    enabled, due, failures, draining = conn.execute(
        "SELECT enabled, next_run_at, failures, draining FROM tl_auto_sync WHERE property_id = %s", (PROPERTY_ID,)
    ).fetchone()
    if not enabled or due > now:
        return
    # Do not take over an initial import (or an explicit restart).
    row = conn.execute("SELECT completed, pages FROM tl_sync_state WHERE property_id = %s", (PROPERTY_ID,)).fetchone()
    if not row or row[1] == 0 or (not row[0] and not draining):
        conn.execute("UPDATE tl_auto_sync SET next_run_at = %s, last_error = 'INITIAL_IMPORT_REQUIRED' WHERE property_id = %s", (now + timedelta(seconds=INTERVAL), PROPERTY_ID))
        return
    try:
        result = update_summaries()
        more = result['has_more_data']
        if not more:
            wake_details(conn)
        # Fetch at most one page per tick; drain a backlog without a tight loop.
        conn.execute("""UPDATE tl_auto_sync SET next_run_at = %s,
            last_success_at = %s, last_error = NULL, failures = 0, draining = %s, updated_at = now()
            WHERE property_id = %s""", (now + timedelta(seconds=5 if more else INTERVAL), now, more, PROPERTY_ID))
    except HTTPException as error:
        failures += 1
        headers = error.headers or {}
        delay = max(30, retry_delay(headers.get('Retry-After'), failures - 1, now))
        # Only our own sanitized messages; do not persist URLs or credentials.
        code = 'SYNC_HTTP_' + str(error.status_code)
        if error.detail == 'TravelLine returned HTTP 429':
            code = 'TRAVELLINE_HTTP_429'
        conn.execute("""UPDATE tl_auto_sync SET next_run_at = %s,
            last_error = %s, failures = %s, updated_at = now() WHERE property_id = %s""",
            (now + timedelta(seconds=delay), code, failures, PROPERTY_ID))


def worker():
    while not _stop.is_set():
        try:
            with connect() as conn:
                conn.autocommit = True
                if not conn.execute("SELECT pg_try_advisory_lock(4950, 4)").fetchone()[0]:
                    _stop.wait(5)
                    continue
                try:
                    # Wait for initial setup rather than creating booking tables here.
                    if conn.execute("SELECT to_regclass('public.tl_sync_state')").fetchone()[0]:
                        with conn.transaction():
                            prepare_auto(conn)
                        poll_once(conn)
                finally:
                    conn.execute("SELECT pg_advisory_unlock(4950, 4)")
            _stop.wait(5)
        except Exception as error:
            logger.error('Automatic synchronization retry: %s', type(error).__name__)
            _stop.wait(30)


def launch_worker():
    global _thread
    if not all(os.environ.get(k) for k in ('PGHOST','PGPORT','PGDATABASE','PGUSER','PGPASSWORD','SYNC_API_KEY','TRAVELLINE_CLIENT_ID','TRAVELLINE_CLIENT_SECRET')):
        return
    with _guard:
        if _thread is None or not _thread.is_alive():
            _stop.clear()
            _thread = threading.Thread(target=worker, name='travelline-auto-sync', daemon=True)
            _thread.start()


def shutdown_worker():
    _stop.set()


@router.get('/status')
def status():
    try:
        with connect() as conn:
            prepare_auto(conn)
            enabled, due, success, error, failures, updated = conn.execute(
                'SELECT enabled, next_run_at, last_success_at, last_error, failures, updated_at FROM tl_auto_sync WHERE property_id = %s', (PROPERTY_ID,)
            ).fetchone()
        return {'status':'ok', 'enabled':enabled, 'interval_seconds':INTERVAL,
                'next_run_at':due, 'last_success_at':success, 'last_error':error,
                'failures':failures, 'updated_at':updated,
                'details_status_path':'/api/storage/details/status'}
    except psycopg.Error:
        raise HTTPException(503, 'Database operation failed') from None


def set_enabled(enabled):
    try:
        with connect() as conn:
            prepare_auto(conn)
            conn.execute('UPDATE tl_auto_sync SET enabled = %s, next_run_at = now(), updated_at = now() WHERE property_id = %s', (enabled, PROPERTY_ID))
        if enabled:
            launch_worker()
        return {'status':'ok', 'enabled':enabled}
    except psycopg.Error:
        raise HTTPException(503, 'Database operation failed') from None


@router.post('/start')
def start():
    return set_enabled(True)


@router.post('/pause')
def pause():
    """Pause summary polling; an in-flight page/details job may finish."""
    return set_enabled(False)
