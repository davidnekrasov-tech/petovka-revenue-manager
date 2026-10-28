"""Protected summary refresh and per-stay audit, without guest contact data."""

import json
import os
from datetime import date, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import psycopg
from psycopg.types.json import Jsonb
from fastapi import APIRouter, Depends, HTTPException

from booking_storage import PROPERTY_ID, authorize, connect, prepare, validate_page
from occupancy import local_date


def fetch_changes(token, since):
    client_id = os.environ.get("TRAVELLINE_CLIENT_ID")
    secret = os.environ.get("TRAVELLINE_CLIENT_SECRET")
    if not client_id or not secret:
        raise HTTPException(503, "TravelLine credentials are missing")
    request = Request(
        "https://partner.tlintegration.com/auth/token",
        data=urlencode({"grant_type": "client_credentials", "client_id": client_id, "client_secret": secret}).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST",
    )
    with urlopen(request, timeout=20) as response:
        access_token = json.load(response)["access_token"]
    query = {"count": 100}
    if token:
        query["continueToken"] = token
    else:
        # Older deployments discarded the final cursor. Re-read a safe overlap.
        query["lastModification"] = (since - timedelta(days=2)).isoformat()
    request = Request(
        "https://partner.tlintegration.com/api/read-reservation/v1/properties/" + PROPERTY_ID + "/bookings?" + urlencode(query),
        headers={"Authorization": "Bearer " + access_token}, method="GET",
    )
    with urlopen(request, timeout=20) as response:
        page = json.load(response)
    return {"status": "ok", "bookings": page.get("bookingSummaries"),
            "has_more_data": page.get("hasMoreData"), "continue_token": page.get("continueToken")}


def validate_changes(page, previous_token):
    # An idle poll can legitimately return the same final cursor.
    bookings, more, token = validate_page(page, previous_token)
    if not isinstance(token, str) or not token:
        raise HTTPException(502, "TravelLine did not return an update cursor")
    return bookings, more, token


router = APIRouter(prefix="/api/storage", tags=["Reconciliation"], dependencies=[Depends(authorize)])


@router.post("/updates")
def update_summaries():
    """Fetch one page of new/changed summaries. Repeat until has_more_data=false."""
    try:
        with connect() as connection:
            prepare(connection)
            token, updated, pages = connection.execute(
                "SELECT next_token, updated_at, pages FROM tl_sync_state WHERE property_id = %s", (PROPERTY_ID,)
            ).fetchone()
            if pages == 0 and not token:
                raise HTTPException(409, "Run the initial summary import first")
            bookings, more, next_token = validate_changes(fetch_changes(token, updated), token)
            changed = 0
            for booking in bookings:
                # Keep unchanged hashes and import timestamps stable during overlap reads.
                row = connection.execute("""
                    INSERT INTO tl_booking_summaries (property_id, booking_number, payload)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (property_id, booking_number) DO UPDATE
                    SET payload = EXCLUDED.payload, synced_at = now()
                    WHERE tl_booking_summaries.payload IS DISTINCT FROM EXCLUDED.payload
                    RETURNING booking_number
                """, (PROPERTY_ID, booking["number"], Jsonb(booking))).fetchone()
                changed += int(row is not None)
            connection.execute("""
                UPDATE tl_sync_state SET next_token = %s, completed = %s,
                    pages = pages + 1, updated_at = now() WHERE property_id = %s
            """, (next_token, not more, PROPERTY_ID))
        return {"status": "ok", "received": len(bookings), "changed": changed,
                "has_more_data": more, "next_step": "Repeat updates" if more else "Start details import, then recalculate occupancy"}
    except HTTPError as error:
        raise HTTPException(502, "TravelLine returned HTTP " + str(error.code)) from None
    except (URLError, TimeoutError):
        raise HTTPException(502, "TravelLine is temporarily unavailable") from None
    except (KeyError, ValueError, TypeError):
        raise HTTPException(502, "Unexpected TravelLine response") from None
    except psycopg.Error:
        raise HTTPException(503, "Database operation failed") from None


def audit_stays(rows, date_from, date_to):
    result = []
    invalid = 0
    for number, summary_status, payload, source_current, synced_at in rows:
        for index, stay in enumerate(payload.get("roomStays", [])):
            try:
                arrival = local_date(stay["stayDates"]["arrivalDateTime"])
                departure = local_date(stay["stayDates"]["departureDateTime"])
            except (KeyError, TypeError, ValueError):
                invalid += 1
                continue
            if departure <= date_from or arrival >= date_to or departure <= arrival:
                continue
            nights = []
            night = max(arrival, date_from)
            while night < min(departure, date_to):
                nights.append(night.isoformat())
                night += timedelta(days=1)
            detail_status = payload.get("status")
            reason = "included"
            if not source_current:
                reason = "stale_details"
            elif summary_status == "Cancelled" or detail_status == "Cancelled":
                reason = "cancelled"
            elif summary_status != "Active" or detail_status != "Active":
                reason = "unsupported_status"
            result.append({
                "booking_number": number, "stay_index": index,
                "summary_status": summary_status, "detail_status": detail_status,
                "category": (stay.get("roomType") or {}).get("name"),
                "arrival": arrival.isoformat(), "departure": departure.isoformat(),
                "nights": nights, "calculation_reason": reason, "detail_import_at": synced_at,
            })
    return {"stays": result, "invalid_stay_dates": invalid}


@router.get("/occupancy/audit")
def audit(date_from: date, date_to: date):
    """List overlapping stored stays and reasons for inclusion/exclusion; checkout exclusive."""
    if not 1 <= (date_to - date_from).days <= 31:
        raise HTTPException(422, "Audit range must contain 1 to 31 nights")
    try:
        with connect() as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            if any(v is None for v in connection.execute("SELECT to_regclass('public.tl_booking_summaries'), to_regclass('public.tl_booking_details')").fetchone()):
                raise HTTPException(409, "Import summaries and details first")
            rows = connection.execute("""
                SELECT s.booking_number, s.payload->>'status', d.payload,
                    d.source_hash = md5(s.payload::text), d.synced_at
                FROM tl_booking_summaries s JOIN tl_booking_details d
                  ON d.property_id = s.property_id AND d.booking_number = s.booking_number
                WHERE s.property_id = %s ORDER BY s.booking_number
            """, (PROPERTY_ID,))
            result = audit_stays(rows, date_from, date_to)
        return {"status": "ok", "date_from": date_from, "date_to_exclusive": date_to,
                "scope": "Stored snapshots; bookings absent from the import cannot appear here", **result}
    except psycopg.Error:
        raise HTTPException(503, "Database operation failed") from None
