"""Privacy-minimized reservation state and 90-day occupancy calculations.

Store only room-night information. Never store guest names, contacts or payment data.
This module is not wired to a scheduled TravelLine sync yet.
"""
import json
import sqlite3
from datetime import date, timedelta


def init_db(connection):
    connection.execute("""CREATE TABLE IF NOT EXISTS reservation_state (
        booking_number TEXT PRIMARY KEY,
        status TEXT NOT NULL,
        stays_json TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    connection.commit()


def normalize_booking(booking):
    """Extract only fields required for occupancy. Unknown status stays non-active."""
    number = booking.get("number")
    if not number:
        raise ValueError("Booking number required")
    stays = []
    for stay in booking.get("roomStays") or []:
        dates = stay.get("stayDates") or {}
        arrival, departure = dates.get("arrivalDateTime"), dates.get("departureDateTime")
        if not arrival or not departure:
            continue
        first, last = date.fromisoformat(arrival[:10]), date.fromisoformat(departure[:10])
        if last <= first:
            continue
        stays.append({
            "arrival": first.isoformat(),
            "departure": last.isoformat(),
            "category": (stay.get("roomType") or {}).get("name") or "Неизвестная категория",
        })
    return str(number), str(booking.get("status") or "Unknown"), stays


def upsert_booking(connection, booking):
    number, status, stays = normalize_booking(booking)
    connection.execute("""INSERT INTO reservation_state (booking_number, status, stays_json)
        VALUES (?, ?, ?)
        ON CONFLICT(booking_number) DO UPDATE SET
        status=excluded.status, stays_json=excluded.stays_json,
        updated_at=CURRENT_TIMESTAMP""",
        (number, status, json.dumps(stays, ensure_ascii=False)))
    connection.commit()


def calendar(connection, start, days=90, inventory=15):
    """Local state only; complete=False until an authoritative initial sync is verified."""
    first = date.fromisoformat(start)
    if not 1 <= days <= 90:
        raise ValueError("days must be between 1 and 90")
    rows = {}
    for offset in range(days):
        day = (first + timedelta(days=offset)).isoformat()
        rows[day] = {"occupied_rooms": 0, "available_rooms": None, "categories": {}}
    for status, stays_json in connection.execute("SELECT status, stays_json FROM reservation_state"):
        if status != "Active":
            continue
        for stay in json.loads(stays_json):
            current = max(first, date.fromisoformat(stay["arrival"]))
            stop = min(first + timedelta(days=days), date.fromisoformat(stay["departure"]))
            while current < stop:
                row = rows[current.isoformat()]
                row["occupied_rooms"] += 1
                cat = stay["category"]
                row["categories"][cat] = row["categories"].get(cat, 0) + 1
                current += timedelta(days=1)
    anomalies = [day for day, row in rows.items() if row["occupied_rooms"] > inventory]
    return {
        "status": "partial",
        "complete": False,
        "safe_for_pricing": False,
        "inventory": inventory,
        "days": rows,
        "anomalies": anomalies,
        "warning": "Local snapshot is not an authoritative inventory or complete TravelLine sync.",
    }
