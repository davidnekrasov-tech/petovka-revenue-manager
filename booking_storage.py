"""Protected, resumable import of TravelLine booking summaries."""

import hmac
import os
from typing import Callable

import psycopg
from psycopg.types.json import Jsonb
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from urllib.error import HTTPError, URLError


bearer = HTTPBearer(auto_error=False)
PROPERTY_ID = "4950"


def authorize(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    expected = os.environ.get("SYNC_API_KEY", "")
    if not expected:
        raise HTTPException(503, "Synchronization is not configured")
    if credentials is None or not hmac.compare_digest(
        credentials.credentials.encode(), expected.encode()
    ):
        raise HTTPException(401, "Invalid synchronization key")


def connect():
    names = ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD")
    if any(not os.environ.get(name) for name in names):
        raise HTTPException(503, "Database is not configured")
    return psycopg.connect(
        host=os.environ["PGHOST"], port=os.environ["PGPORT"],
        dbname=os.environ["PGDATABASE"], user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"], connect_timeout=5,
        options="-c statement_timeout=5000 -c lock_timeout=3000",
    )


def prepare(connection):
    # Serialize schema creation and imports across all workers/requests.
    acquired = connection.execute(
        "SELECT pg_try_advisory_xact_lock(4950, 1)"
    ).fetchone()[0]
    if not acquired:
        raise HTTPException(409, "Another synchronization is running")
    connection.execute("""
        CREATE TABLE IF NOT EXISTS tl_booking_summaries (
            property_id text NOT NULL,
            booking_number text NOT NULL,
            payload jsonb NOT NULL,
            synced_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (property_id, booking_number)
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS tl_sync_state (
            property_id text PRIMARY KEY,
            next_token text,
            completed boolean NOT NULL DEFAULT false,
            pages integer NOT NULL DEFAULT 0,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    connection.execute(
        "INSERT INTO tl_sync_state (property_id) VALUES (%s) "
        "ON CONFLICT DO NOTHING", (PROPERTY_ID,),
    )


def validate_page(page, previous_token):
    if not isinstance(page, dict) or page.get("status") != "ok":
        raise HTTPException(502, "Unexpected TravelLine response")
    bookings = page.get("bookings")
    more = page.get("has_more_data")
    token = page.get("continue_token")
    if not isinstance(bookings, list) or not isinstance(more, bool):
        raise HTTPException(502, "Invalid TravelLine pagination response")
    if more and (not isinstance(token, str) or not token or token == previous_token):
        raise HTTPException(502, "TravelLine pagination did not advance")
    for booking in bookings:
        if not isinstance(booking, dict) or not isinstance(booking.get("number"), str) or not booking["number"]:
            raise HTTPException(502, "TravelLine booking number is missing")
    return bookings, more, token if more else None


def make_router(fetch_page: Callable):
    router = APIRouter(
        prefix="/api/storage", tags=["Database synchronization"],
        dependencies=[Depends(authorize)],
    )

    @router.post("/init")
    def initialize():
        try:
            with connect() as connection:
                prepare(connection)
            return {"status": "ok", "tables": "ready"}
        except psycopg.Error:
            raise HTTPException(503, "Database operation failed") from None

    @router.post("/sync")
    def sync_page():
        """Import one page (up to 100 summaries). Repeat until completed=true."""
        try:
            with connect() as connection:
                prepare(connection)
                token, completed, pages = connection.execute(
                    "SELECT next_token, completed, pages FROM tl_sync_state "
                    "WHERE property_id = %s", (PROPERTY_ID,),
                ).fetchone()
                if completed:
                    return {"status": "ok", "completed": True, "saved": 0, "pages": pages}
                bookings, more, next_token = validate_page(fetch_page(token), token)
                for booking in bookings:
                    connection.execute("""
                        INSERT INTO tl_booking_summaries
                            (property_id, booking_number, payload)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (property_id, booking_number)
                        DO UPDATE SET payload = EXCLUDED.payload, synced_at = now()
                    """, (PROPERTY_ID, booking["number"], Jsonb(booking)))
                connection.execute("""
                    UPDATE tl_sync_state SET next_token = %s, completed = %s,
                        pages = pages + 1, updated_at = now()
                    WHERE property_id = %s
                """, (next_token, not more, PROPERTY_ID))
            return {"status": "ok", "saved": len(bookings), "completed": not more, "pages": pages + 1}
        except HTTPError as error:
            raise HTTPException(502, f"TravelLine returned HTTP {error.code}") from None
        except (URLError, TimeoutError):
            raise HTTPException(502, "TravelLine is temporarily unavailable") from None
        except (ValueError, KeyError, TypeError):
            raise HTTPException(502, "Unexpected TravelLine response") from None
        except psycopg.Error:
            raise HTTPException(503, "Database operation failed") from None

    @router.get("/status")
    def status():
        try:
            with connect() as connection:
                prepare(connection)
                count = connection.execute(
                    "SELECT count(*) FROM tl_booking_summaries WHERE property_id = %s",
                    (PROPERTY_ID,),
                ).fetchone()[0]
                completed, pages, updated = connection.execute(
                    "SELECT completed, pages, updated_at FROM tl_sync_state WHERE property_id = %s",
                    (PROPERTY_ID,),
                ).fetchone()
            return {"status": "ok", "stored_bookings": count,
                    "completed": completed, "pages": pages, "updated_at": updated}
        except psycopg.Error:
            raise HTTPException(503, "Database operation failed") from None

    @router.post("/restart")
    def restart():
        """Restart pagination without deleting previously saved bookings."""
        try:
            with connect() as connection:
                prepare(connection)
                connection.execute(
                    "UPDATE tl_sync_state SET next_token = NULL, completed = false, "
                    "pages = 0, updated_at = now() WHERE property_id = %s", (PROPERTY_ID,),
                )
            return {"status": "ok", "completed": False}
        except psycopg.Error:
            raise HTTPException(503, "Database operation failed") from None

    return router
