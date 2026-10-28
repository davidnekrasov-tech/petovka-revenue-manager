"""Read-only room-night calculations from imported TravelLine snapshots."""

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import psycopg
from fastapi import APIRouter, Depends, HTTPException

from booking_storage import PROPERTY_ID, authorize, connect
from pricing import HOTEL_CAPACITY, ROOM_CATEGORIES


def normalized(value):
    return " ".join(value.casefold().replace("ё", "е").split())


ALIASES = {normalized(name): name for name in ROOM_CATEGORIES}
for alias, name in zip(
    ("Одноместный", "Стандарт", "Улучшенный", "Комфорт"), ROOM_CATEGORIES
):
    ALIASES[normalized(alias)] = name


def local_date(value):
    if not isinstance(value, str):
        raise ValueError("Date must be a string")
    # TravelLine stay dates are local hotel dates. Do not convert to UTC.
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def money(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value))
        return amount if amount.is_finite() and amount >= 0 else None
    except (InvalidOperation, ValueError):
        return None


def amount_text(value):
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


def bucket():
    return {"occupied": 0, "priced": 0, "known_amount": Decimal("0")}


def finish_bucket(value, capacity):
    occupied = value["occupied"]
    complete = occupied == value["priced"]
    return {
        "capacity": capacity,
        "occupied": occupied,
        "available": max(0, capacity - occupied),
        "over_capacity": max(0, occupied - capacity),
        "occupancy_percent": round(occupied / capacity * 100, 1),
        "priced_room_nights": value["priced"],
        "missing_price_room_nights": occupied - value["priced"],
        "known_room_amount_before_tax": amount_text(value["known_amount"]),
        "room_amount_before_tax": amount_text(value["known_amount"]) if complete else None,
        "price_data_complete": complete,
    }


def calculate_occupancy(records, date_from, date_to):
    """records: (sanitized booking detail, latest imported summary status)."""
    if not 1 <= (date_to - date_from).days <= 366:
        raise ValueError("Range must contain between 1 and 366 nights")
    days = {}
    current = date_from
    while current < date_to:
        days[current] = {
            "total": bucket(),
            "categories": {name: bucket() for name in ROOM_CATEGORIES},
            "unknown": {},
        }
        current += timedelta(days=1)
    issues = {}

    def issue(code):
        issues[code] = issues.get(code, 0) + 1

    for booking, summary_status in records:
        if not isinstance(booking, dict):
            issue("invalid_booking_payload")
            continue
        if summary_status == "Cancelled" or booking.get("status") == "Cancelled":
            continue
        if summary_status != "Active" or booking.get("status") != "Active":
            issue("unsupported_booking_status")
            continue
        stays = booking.get("roomStays")
        if not isinstance(stays, list):
            issue("invalid_room_stays")
            continue
        for stay in stays:
            try:
                dates = stay["stayDates"]
                arrival = local_date(dates["arrivalDateTime"])
                departure = local_date(dates["departureDateTime"])
            except (KeyError, TypeError, ValueError):
                issue("invalid_stay_dates")
                continue
            if departure < arrival:
                issue("reversed_stay_dates")
                continue
            if departure == arrival or departure <= date_from or arrival >= date_to:
                continue
            room_type = stay.get("roomType") or {}
            name = room_type.get("name", "") if isinstance(room_type, dict) else ""
            category = ALIASES.get(normalized(name)) if isinstance(name, str) else None
            if category is None:
                issue("unknown_room_category")
            rates = {}
            for rate in stay.get("dailyRates", []) or []:
                try:
                    rate_date = local_date(rate["date"])
                    amount = money(rate.get("priceBeforeTax"))
                    # Duplicate rates for one room-night are ambiguous, not additive.
                    rates[rate_date] = None if rate_date in rates else amount
                except (KeyError, TypeError, ValueError):
                    issue("invalid_daily_rate")
            night = max(arrival, date_from)
            while night < min(departure, date_to):
                day = days[night]
                targets = [day["total"]]
                if category:
                    targets.append(day["categories"][category])
                else:
                    unknown_name = name if isinstance(name, str) and name else "Без названия"
                    day["unknown"][unknown_name] = day["unknown"].get(unknown_name, 0) + 1
                amount = rates.get(night) if booking.get("currencyCode") == "RUB" else None
                for target in targets:
                    target["occupied"] += 1
                    if amount is not None:
                        target["priced"] += 1
                        target["known_amount"] += amount
                night += timedelta(days=1)

    result = []
    for night, day in days.items():
        value = {"date": night.isoformat(), **finish_bucket(day["total"], HOTEL_CAPACITY)}
        value["categories"] = {
            name: finish_bucket(day["categories"][name], config["capacity"])
            for name, config in ROOM_CATEGORIES.items()
        }
        value["unknown_categories"] = day["unknown"]
        if value["over_capacity"] or any(c["over_capacity"] for c in value["categories"].values()):
            issue("inventory_exceeded")
        result.append(value)
    return {"dates": result, "quality_issues": issues}


router = APIRouter(prefix="/api/storage", tags=["Occupancy from database"], dependencies=[Depends(authorize)])


@router.get("/occupancy")
def occupancy(date_from: date, date_to: date):
    """date_to is checkout date (exclusive); money is nightly RUB before tax, not payments."""
    if not 1 <= (date_to - date_from).days <= 366:
        raise HTTPException(422, "date_to must be 1 to 366 nights after date_from")
    try:
        with connect() as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            tables = connection.execute("SELECT to_regclass('public.tl_booking_summaries'), to_regclass('public.tl_booking_details'), to_regclass('public.tl_sync_state')").fetchone()
            if any(table is None for table in tables):
                raise HTTPException(409, "Import booking summaries and details first")
            total, current, last_summary_sync, last_detail_sync = connection.execute("""
                SELECT count(*), count(d.booking_number), max(s.synced_at), max(d.synced_at)
                FROM tl_booking_summaries s LEFT JOIN tl_booking_details d
                  ON d.property_id = s.property_id AND d.booking_number = s.booking_number
                  AND d.source_hash = md5(s.payload::text)
                WHERE s.property_id = %s
            """, (PROPERTY_ID,)).fetchone()
            state = connection.execute("SELECT completed FROM tl_sync_state WHERE property_id = %s", (PROPERTY_ID,)).fetchone()
            summaries_complete = bool(state and state[0])
            rows = connection.execute("""
                SELECT d.payload, s.payload->>'status'
                FROM tl_booking_details d JOIN tl_booking_summaries s
                  ON s.property_id = d.property_id AND s.booking_number = d.booking_number
                  AND d.source_hash = md5(s.payload::text)
                WHERE d.property_id = %s
            """, (PROPERTY_ID,))
            calculation = calculate_occupancy(rows, date_from, date_to)
        return {
            "status": "ok", "property_id": PROPERTY_ID,
            "date_from": date_from, "date_to_exclusive": date_to,
            "currency": "RUB", "amount_basis": "dailyRates.priceBeforeTax; not collected payments",
            "coverage": {
                "summary_bookings": total, "current_details": current,
                "missing_or_stale_details": total - current,
                "summary_import_completed": summaries_complete,
                "imported_dataset_complete": total > 0 and total == current and summaries_complete,
                "last_summary_import_at": last_summary_sync,
                "last_detail_import_at": last_detail_sync,
                "scope": "Imported summaries modified since 2023-09-22; not a live TravelLine query",
            },
            **calculation,
        }
    except psycopg.Error:
        raise HTTPException(503, "Database operation failed") from None
