"""Read-only TravelLine -> local SQLite synchronization worker.

Run as a private worker on a host with persistent storage, never as a public GET endpoint.
A full historical backfill requires a separately verified start date and capacity plan.
"""
import os
import sqlite3
import time
from urllib.parse import urlencode, quote
from occupancy_service import BASE, PROPERTY, _json_request
from reservation_store import init_db, upsert_booking


def sync_batch(db_path, start_modification, max_pages=1, max_details=50):
    """Safely sample changed bookings; cursor is NOT advanced past incomplete detail reads."""
    if not os.path.isabs(db_path):
        raise ValueError("Database path must be absolute on persistent storage")
    if not (1 <= max_pages <= 5 and 1 <= max_details <= 100):
        raise ValueError("Sync limits out of bounds")
    client_id = os.environ["TRAVELLINE_CLIENT_ID"]
    client_secret = os.environ["TRAVELLINE_CLIENT_SECRET"]
    token = _json_request(BASE + "/auth/token", form=urlencode({
        "grant_type": "client_credentials", "client_id": client_id,
        "client_secret": client_secret}).encode())["access_token"]
    connection = sqlite3.connect(db_path)
    try:
        init_db(connection)
        cursor = None
        seen = set()
        written = 0
        pages = 0
        errors = 0
        exhausted = False
        for _ in range(max_pages):
            params = {"count": min(max_details, 100)}
            if cursor:
                params["continueToken"] = cursor
            else:
                params["lastModification"] = start_modification
            listing = _json_request(BASE + "/api/read-reservation/v1/properties/" +
                                    PROPERTY + "/bookings?" + urlencode(params), token=token)
            summaries = listing.get("bookingSummaries") or []
            pages += 1
            for item in summaries:
                number = item.get("number")
                if not number or number in seen:
                    continue
                seen.add(number)
                time.sleep(0.4)
                try:
                    details = _json_request(BASE + "/api/read-reservation/v1/properties/" +
                                            PROPERTY + "/bookings/" + quote(str(number), safe=""),
                                            token=token)
                    booking = details.get("booking")
                    if not booking:
                        raise ValueError("Missing booking details")
                    upsert_booking(connection, booking)
                    written += 1
                except Exception:
                    # Fail closed: do not pretend that a partial page was synchronized.
                    errors += 1
            if errors:
                break
            exhausted = not bool(listing.get("hasMoreData"))
            if exhausted:
                break
            next_cursor = listing.get("continueToken")
            if not next_cursor or next_cursor == cursor:
                errors += 1
                break
            cursor = next_cursor
        return {
            "status": "complete_sample" if exhausted and not errors else "partial",
            "pages_scanned": pages,
            "bookings_saved": written,
            "errors": errors,
            "has_more_data": not exhausted,
            "checkpoint_saved": False,
            "safe_for_pricing": False,
            "note": "No automatic checkpoint or scheduled execution. Run again from a known safe modification date.",
        }
    finally:
        connection.close()
