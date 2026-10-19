"""Bounded TravelLine occupancy diagnostics; NOT a complete PMS occupancy feed."""
import json
import os
import time
from datetime import date, timedelta
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BASE = "https://partner.tlintegration.com"
PROPERTY = "4950"


def _json_request(url, token=None, form=None):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if form is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = Request(url, headers=headers, data=form, method="POST" if form is not None else "GET")
    with urlopen(request, timeout=20) as response:
        return json.load(response)


def aggregate_stays(bookings, start, end):
    """Count occupied room-nights, excluding departure day and duplicate bookings."""
    dates = {}
    seen_bookings = set()
    for booking in bookings:
        booking_id = booking.get("number") or booking.get("id")
        if booking_id is not None:
            if booking_id in seen_bookings:
                continue
            seen_bookings.add(booking_id)
        if booking.get("status") not in ("Active", None):
            continue
        for stay in booking.get("roomStays", []):
            sd = stay.get("stayDates") or {}
            arrival, departure = sd.get("arrivalDateTime"), sd.get("departureDateTime")
            if not arrival or not departure:
                continue
            try:
                first, last = date.fromisoformat(arrival[:10]), date.fromisoformat(departure[:10])
            except ValueError:
                continue
            category = (stay.get("roomType") or {}).get("name") or "Неизвестная категория"
            current = max(first, start)
            while current < min(last, end + timedelta(days=1)):
                key = current.isoformat()
                row = dates.setdefault(key, {"rooms": 0, "categories": {}})
                row["rooms"] += 1
                row["categories"][category] = row["categories"].get(category, 0) + 1
                current += timedelta(days=1)
    return dates


def occupancy_diagnostic(start_date, end_date, max_pages=3, max_details=60):
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if end < start or (end - start).days > 31:
        raise ValueError("Date range must be 1–32 days")
    client_id = os.getenv("TRAVELLINE_CLIENT_ID")
    client_secret = os.getenv("TRAVELLINE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("TravelLine credentials are not configured")
    token_data = _json_request(
        BASE + "/auth/token",
        form=urlencode({"grant_type": "client_credentials", "client_id": client_id,
                        "client_secret": client_secret}).encode(),
    )
    token = token_data["access_token"]
    summaries = []
    cursor = None
    has_more = True
    errors = []
    pages_scanned = 0
    for page in range(max_pages):
        params = {"count": 100}
        if cursor:
            params["continueToken"] = cursor
        else:
            # Modification date is NOT stay date. This is only a bounded diagnostic.
            params["lastModification"] = "2026-09-16T00:00:00Z"
        try:
            batch = _json_request(
                BASE + "/api/read-reservation/v1/properties/" + PROPERTY + "/bookings?" + urlencode(params),
                token=token,
            )
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            errors.append("Listing page failed: " + type(exc).__name__)
            break
        pages_scanned += 1
        summaries.extend(batch.get("bookingSummaries") or [])
        has_more = bool(batch.get("hasMoreData"))
        next_cursor = batch.get("continueToken")
        if not has_more:
            break
        if not next_cursor or next_cursor == cursor:
            errors.append("Missing or repeated continuation token")
            break
        cursor = next_cursor

    seen = set()
    active = []
    for item in summaries:
        number = item.get("number")
        if item.get("status") == "Active" and number and number not in seen:
            seen.add(number)
            active.append(number)
    details = []
    for number in active[:max_details]:
        # Conservative request pacing; avoid hammering TravelLine.
        time.sleep(0.4)
        url = BASE + "/api/read-reservation/v1/properties/" + PROPERTY + "/bookings/" + quote(str(number), safe="")
        try:
            payload = _json_request(url, token=token)
            booking = payload.get("booking") or {}
            if booking.get("status", "Active") == "Active":
                details.append(booking)
        except (HTTPError, URLError, TimeoutError, ValueError):
            errors.append("Failed to load booking detail")
    return {
        "status": "partial",
        "complete": False,
        "safe_for_pricing": False,
        "date_from": start_date,
        "date_to": end_date,
        "dates": aggregate_stays(details, start, end),
        "summaries_scanned": len(summaries),
        "pages_scanned": pages_scanned,
        "active_unique_found": len(active),
        "details_loaded": len(details),
        "has_more_data": has_more,
        "details_truncated": len(active) > max_details,
        "errors": errors,
        "warning": "INCOMPLETE: only recently modified bookings were sampled. Missing dates are unknown, not zero. Do not price from this endpoint.",
    }
