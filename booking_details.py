"""Resumable background import of operational booking details (no guest contacts)."""

import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import psycopg
from psycopg.types.json import Jsonb
from fastapi import APIRouter, Depends, HTTPException

from booking_storage import PROPERTY_ID, authorize, connect, prepare


logger = logging.getLogger(__name__)
_guard = threading.Lock()
_thread = None
_shutdown = threading.Event()
AUTH_URL = "https://partner.tlintegration.com/auth/token"
BOOKING_URL = "https://partner.tlintegration.com/api/read-reservation/v1/properties/"


def retry_delay(value, attempt=0, now=None):
    """Honor Retry-After seconds or HTTP-date; exponential fallback on 429."""
    now = now or datetime.now(timezone.utc)
    fallback = min(120 * 2 ** min(attempt, 5), 1800)
    try:
        return max(1, float(value))
    except (TypeError, ValueError):
        try:
            return max(1, (parsedate_to_datetime(value) - now).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return fallback


def select_details(payload, expected_number):
    """Allowlist business fields: guest names/phones/emails never enter this table."""
    booking = payload.get("booking") if isinstance(payload, dict) else None
    if not isinstance(booking, dict) or booking.get("number") != expected_number:
        raise ValueError("Invalid booking envelope")
    stays = booking.get("roomStays")
    if not isinstance(stays, list) or not isinstance(booking.get("status"), str):
        raise ValueError("Invalid room stays or status")
    clean_stays = []
    for stay in stays:
        if not isinstance(stay, dict):
            raise ValueError("Invalid room stay")
        clean = {}
        for field, allowed in (
            ("stayDates", ("arrivalDateTime", "departureDateTime")),
            ("roomType", ("id", "name")),
            ("guestCount", ("adultCount", "childCount")),
            ("total", ("amount", "currencyCode", "priceBeforeTax", "priceAfterTax", "taxAmount")),
        ):
            value = stay.get(field)
            if isinstance(value, dict):
                clean[field] = {k: value[k] for k in allowed if k in value}
            elif isinstance(value, (int, float, str)) and field == "total":
                clean[field] = value
        rates = stay.get("dailyRates", [])
        if not isinstance(rates, list):
            raise ValueError("Invalid daily rates")
        clean["dailyRates"] = [
            {k: rate[k] for k in ("date", "price", "amount", "currencyCode", "priceBeforeTax", "priceAfterTax", "taxAmount", "ratePlanId") if k in rate}
            for rate in rates if isinstance(rate, dict)
        ]
        # Nested price objects may contain extensions; retain only monetary fields.
        for rate in clean["dailyRates"]:
            if isinstance(rate.get("price"), dict):
                rate["price"] = {k: rate["price"][k] for k in ("amount", "currencyCode", "priceBeforeTax", "priceAfterTax", "taxAmount") if k in rate["price"]}
        clean_stays.append(clean)
    result = {k: booking[k] for k in (
        "number", "status", "currencyCode", "createdDateTime", "lastModifiedDateTime", "lastModification"
    ) if k in booking}
    total = booking.get("total")
    if isinstance(total, dict):
        result["total"] = {k: total[k] for k in ("amount", "currencyCode", "priceBeforeTax", "priceAfterTax", "taxAmount") if k in total}
    elif isinstance(total, (int, float, str)):
        result["total"] = total
    result["roomStays"] = clean_stays
    return result


class TravelLineClient:
    def __init__(self):
        self.token = None
        self.expires = 0

    def get_booking(self, number):
        if not self.token or time.monotonic() >= self.expires:
            client_id = os.environ.get("TRAVELLINE_CLIENT_ID")
            secret = os.environ.get("TRAVELLINE_CLIENT_SECRET")
            if not client_id or not secret:
                raise ValueError("Missing TravelLine credentials")
            request = Request(AUTH_URL, data=urlencode({
                "grant_type": "client_credentials", "client_id": client_id,
                "client_secret": secret,
            }).encode(), headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
            with urlopen(request, timeout=20) as response:
                token_data = json.load(response)
            self.token = token_data["access_token"]
            self.expires = time.monotonic() + max(1, int(token_data.get("expires_in", 900)) - 60)
        request = Request(
            BOOKING_URL + PROPERTY_ID + "/bookings/" + quote(number, safe=""),
            headers={"Authorization": "Bearer " + self.token}, method="GET",
        )
        try:
            with urlopen(request, timeout=20) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code == 401:
                self.token = None
            raise


def prepare_details(connection):
    connection.execute("SELECT pg_advisory_xact_lock(4950, 3)")
    connection.execute("""
        CREATE TABLE IF NOT EXISTS tl_booking_details (
            property_id text NOT NULL, booking_number text NOT NULL,
            source_hash text NOT NULL, payload jsonb NOT NULL,
            synced_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (property_id, booking_number)
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS tl_detail_errors (
            property_id text NOT NULL, booking_number text NOT NULL,
            source_hash text NOT NULL, error_code text NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (property_id, booking_number)
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS tl_detail_job (
            property_id text PRIMARY KEY, state text NOT NULL DEFAULT 'paused',
            last_error text, retry_at timestamptz,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    connection.execute("INSERT INTO tl_detail_job (property_id) VALUES (%s) ON CONFLICT DO NOTHING", (PROPERTY_ID,))


# Hashes invalidate a detail snapshot only when its summary payload changes.
PENDING_SQL = """
    FROM tl_booking_summaries s
    LEFT JOIN tl_booking_details d ON (d.property_id = s.property_id AND d.booking_number = s.booking_number)
    LEFT JOIN tl_detail_errors e ON (e.property_id = s.property_id AND e.booking_number = s.booking_number)
    WHERE s.property_id = %s
      AND (d.source_hash IS DISTINCT FROM md5(s.payload::text))
      AND (e.source_hash IS DISTINCT FROM md5(s.payload::text))
"""


def set_job(connection, *, error=None, retry_at=None):
    # Never overwrite the user's pause request from an in-flight operation.
    connection.execute("""
        UPDATE tl_detail_job SET last_error = %s, retry_at = %s, updated_at = now()
        WHERE property_id = %s
    """, (error, retry_at, PROPERTY_ID))


def save_detail(connection, number, source_hash, payload):
    with connection.transaction():
        connection.execute("""
            INSERT INTO tl_booking_details (property_id, booking_number, source_hash, payload)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (property_id, booking_number) DO UPDATE SET
                source_hash = EXCLUDED.source_hash, payload = EXCLUDED.payload, synced_at = now()
        """, (PROPERTY_ID, number, source_hash, Jsonb(payload)))
        connection.execute("DELETE FROM tl_detail_errors WHERE property_id = %s AND booking_number = %s", (PROPERTY_ID, number))
        set_job(connection)


def save_error(connection, number, source_hash, code):
    with connection.transaction():
        connection.execute("""
            INSERT INTO tl_detail_errors (property_id, booking_number, source_hash, error_code)
            VALUES (%s, %s, %s, %s) ON CONFLICT (property_id, booking_number)
            DO UPDATE SET source_hash = EXCLUDED.source_hash,
                error_code = EXCLUDED.error_code, updated_at = now()
        """, (PROPERTY_ID, number, source_hash, code))
        set_job(connection, error=code)


def process_job(connection, client):
    failures = 0
    while not _shutdown.is_set():
        state, retry_at = connection.execute(
            "SELECT state, retry_at FROM tl_detail_job WHERE property_id = %s", (PROPERTY_ID,)
        ).fetchone()
        if state != "running":
            return
        if retry_at and retry_at > datetime.now(timezone.utc):
            _shutdown.wait(min(5, (retry_at - datetime.now(timezone.utc)).total_seconds()))
            continue
        pending = connection.execute(
            "SELECT s.booking_number, md5(s.payload::text) " + PENDING_SQL + " ORDER BY s.booking_number LIMIT 1",
            (PROPERTY_ID,),
        ).fetchone()
        if pending is None:
            connection.execute("""
                UPDATE tl_detail_job SET state = 'completed', retry_at = NULL, updated_at = now()
                WHERE property_id = %s AND state = 'running'
            """, (PROPERTY_ID,))
            return
        number, source_hash = pending
        try:
            payload = select_details(client.get_booking(number), number)
            save_detail(connection, number, source_hash, payload)
            failures = 0
        except HTTPError as error:
            code = "HTTP_" + str(error.code)
            if error.code == 404:
                save_error(connection, number, source_hash, code)
                failures = 0
            elif error.code == 429 or error.code >= 500 or error.code == 401:
                failures += 1
                if failures >= 8:
                    connection.execute("UPDATE tl_detail_job SET state = 'failed', last_error = %s, retry_at = NULL, updated_at = now() WHERE property_id = %s AND state = 'running'", (code, PROPERTY_ID))
                    return
                delay = retry_delay(error.headers.get("Retry-After"), failures - 1)
                set_job(connection, error=code, retry_at=datetime.now(timezone.utc) + timedelta(seconds=delay))
            else:
                connection.execute("UPDATE tl_detail_job SET state = 'failed', last_error = %s, updated_at = now() WHERE property_id = %s AND state = 'running'", (code, PROPERTY_ID))
                return
        except (URLError, TimeoutError):
            failures += 1
            if failures >= 8:
                connection.execute("UPDATE tl_detail_job SET state = 'failed', last_error = 'NETWORK_ERROR', retry_at = NULL, updated_at = now() WHERE property_id = %s AND state = 'running'", (PROPERTY_ID,))
                return
            set_job(connection, error="NETWORK_ERROR", retry_at=datetime.now(timezone.utc) + timedelta(seconds=min(30 * 2 ** failures, 600)))
        except (ValueError, KeyError, TypeError):
            # Stop for inspection rather than silently skipping incompatible responses.
            connection.execute("UPDATE tl_detail_job SET state = 'failed', last_error = 'INVALID_RESPONSE_OR_CONFIG', updated_at = now() WHERE property_id = %s AND state = 'running'", (PROPERTY_ID,))
            return
        # One request at a time; cached OAuth token avoids per-booking token requests.
        _shutdown.wait(1)


def worker():
    while not _shutdown.is_set():
        try:
            with connect() as connection:
                connection.autocommit = True
                exists = connection.execute("SELECT to_regclass('public.tl_detail_job')").fetchone()[0]
                locked = exists and connection.execute("SELECT pg_try_advisory_lock(4950, 2)").fetchone()[0]
                if locked:
                    try:
                        process_job(connection, TravelLineClient())
                    finally:
                        connection.execute("SELECT pg_advisory_unlock(4950, 2)")
            # Also closes the startup/start race and retries a lock held by an old deployment.
            _shutdown.wait(5)
        except Exception as error:
            # Log only exception class: never URLs, credentials, booking or guest data.
            logger.error("Detail import worker stopped: %s", type(error).__name__)
            _shutdown.wait(30)


def launch_worker():
    global _thread
    if not all(os.environ.get(name) for name in (
        "PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD", "SYNC_API_KEY"
    )):
        return
    with _guard:
        if _thread is None or not _thread.is_alive():
            _shutdown.clear()
            _thread = threading.Thread(target=worker, name="travelline-details", daemon=True)
            _thread.start()


def shutdown_worker():
    _shutdown.set()


router = APIRouter(prefix="/api/storage/details", tags=["Booking details"], dependencies=[Depends(authorize)])


@router.post("/start", status_code=202)
def start():
    if not all(os.environ.get(name) for name in ("TRAVELLINE_CLIENT_ID", "TRAVELLINE_CLIENT_SECRET")):
        raise HTTPException(503, "TravelLine credentials are missing")
    try:
        with connect() as connection:
            prepare(connection)
            prepare_details(connection)
            completed = connection.execute("SELECT completed FROM tl_sync_state WHERE property_id = %s", (PROPERTY_ID,)).fetchone()[0]
            if not completed:
                raise HTTPException(409, "Complete the booking-summary import first")
            connection.execute("UPDATE tl_detail_job SET state = 'running', last_error = NULL, updated_at = now() WHERE property_id = %s", (PROPERTY_ID,))
        launch_worker()
        return {"status": "accepted", "message": "Background import started; check details/status"}
    except psycopg.Error:
        raise HTTPException(503, "Database operation failed") from None


@router.post("/pause")
def pause():
    try:
        with connect() as connection:
            prepare_details(connection)
            connection.execute("UPDATE tl_detail_job SET state = 'paused', updated_at = now() WHERE property_id = %s", (PROPERTY_ID,))
        return {"status": "ok", "state": "paused"}
    except psycopg.Error:
        raise HTTPException(503, "Database operation failed") from None


@router.get("/status")
def status():
    try:
        with connect() as connection:
            prepare(connection)
            prepare_details(connection)
            total = connection.execute("SELECT count(*) FROM tl_booking_summaries WHERE property_id = %s", (PROPERTY_ID,)).fetchone()[0]
            saved = connection.execute("SELECT count(*) FROM tl_booking_summaries s JOIN tl_booking_details d USING (property_id, booking_number) WHERE s.property_id = %s AND d.source_hash = md5(s.payload::text)", (PROPERTY_ID,)).fetchone()[0]
            errors = connection.execute("SELECT count(*) FROM tl_booking_summaries s JOIN tl_detail_errors e USING (property_id, booking_number) WHERE s.property_id = %s AND e.source_hash = md5(s.payload::text)", (PROPERTY_ID,)).fetchone()[0]
            pending = connection.execute("SELECT count(*) " + PENDING_SQL, (PROPERTY_ID,)).fetchone()[0]
            state, error, retry_at, updated = connection.execute("SELECT state, last_error, retry_at, updated_at FROM tl_detail_job WHERE property_id = %s", (PROPERTY_ID,)).fetchone()
        return {"status": "ok", "state": state, "total": total, "saved": saved,
                "pending": pending, "errors": errors, "completed": state == "completed" and pending == 0 and errors == 0,
                "last_error": error, "retry_at": retry_at, "updated_at": updated}
    except psycopg.Error:
        raise HTTPException(503, "Database operation failed") from None
