"""Creation cohorts of currently active bookings; not historical net pickup."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from booking_storage import PROPERTY_ID, authorize, connect
from occupancy import calculate_occupancy, local_date

router = APIRouter(prefix='/api/storage', tags=['Booking pace'], dependencies=[Depends(authorize)])


def created_at(value):
    if not isinstance(value, str):
        raise ValueError('Missing creation timestamp')
    value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    # Naive TravelLine timestamps are interpreted in the hotel's timezone.
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo('Europe/Moscow'))
    return value.astimezone(timezone.utc)


def calculate_pace(records, date_from, date_to, now):
    if not 1 <= (date_to-date_from).days <= 90:
        raise ValueError('Range must contain 1 to 90 nights')
    if now.tzinfo is None:
        raise ValueError('now must be timezone aware')
    now = now.astimezone(timezone.utc)
    cohorts = {days: [] for days in (1, 3, 7)}
    issues = {}
    unknown_creation = 0
    for booking, status in records:
        if status != 'Active' or booking.get('status') != 'Active':
            continue
        overlaps = False
        for stay in booking.get('roomStays', []):
            try:
                arrival = local_date(stay['stayDates']['arrivalDateTime'])
                departure = local_date(stay['stayDates']['departureDateTime'])
                overlaps |= arrival < date_to and departure > date_from and departure > arrival
            except (KeyError, TypeError, ValueError):
                issues['invalid_stay_dates'] = issues.get('invalid_stay_dates', 0) + 1
        if not overlaps:
            continue
        try:
            creation = created_at(booking.get('createdDateTime'))
            if creation > now:
                raise ValueError('Future creation')
        except (ValueError, TypeError):
            unknown_creation += 1
            continue
        for days in cohorts:
            if now-timedelta(days=days) < creation <= now:
                cohorts[days].append((booking, status))
    windows = []
    for days, rows in cohorts.items():
        calc = calculate_occupancy(rows, date_from, date_to)
        windows.append({
            'days': days, 'from_exclusive': now-timedelta(days=days), 'to_inclusive': now,
            'known_currently_active_bookings_created': len(rows),
            'currently_active_bookings_created': len(rows) if not unknown_creation else None,
            'creation_coverage_complete': unknown_creation == 0,
            'known_active_room_nights': sum(d['occupied'] for d in calc['dates']),
            'dates': [{'date': d['date'], 'known_active_rooms_created': d['occupied'],
                       'categories': {name: c['occupied'] for name,c in d['categories'].items()}}
                      for d in calc['dates']],
            'quality_issues': calc['quality_issues'],
            'cancellations': None, 'net_pickup': None,
        })
    return {'generated_at': now, 'windows': windows,
            'active_overlapping_bookings_without_valid_creation': unknown_creation,
            'quality_issues': issues}


@router.get('/pace')
def pace(date_from: date, date_to: date):
    """Rolling 24/72/168-hour cohorts of active bookings for stay nights in range."""
    if not 1 <= (date_to-date_from).days <= 90:
        raise HTTPException(422, 'Range must contain 1 to 90 nights')
    now = datetime.now(timezone.utc)
    try:
        with connect() as connection:
            connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            tables = connection.execute("SELECT to_regclass('public.tl_booking_summaries'), to_regclass('public.tl_booking_details'), to_regclass('public.tl_sync_state')").fetchone()
            if any(t is None for t in tables):
                raise HTTPException(409, 'Import summaries and details first')
            total = connection.execute('SELECT count(*) FROM tl_booking_summaries WHERE property_id=%s', (PROPERTY_ID,)).fetchone()[0]
            current = connection.execute('''SELECT count(*) FROM tl_booking_summaries s
                JOIN tl_booking_details d USING (property_id, booking_number)
                WHERE s.property_id=%s AND d.source_hash=md5(s.payload::text)''', (PROPERTY_ID,)).fetchone()[0]
            state = connection.execute('SELECT completed, updated_at FROM tl_sync_state WHERE property_id=%s', (PROPERTY_ID,)).fetchone()
            rows = connection.execute('''SELECT d.payload, s.payload->>'status'
                FROM tl_booking_summaries s JOIN tl_booking_details d USING (property_id, booking_number)
                WHERE s.property_id=%s AND d.source_hash=md5(s.payload::text)''', (PROPERTY_ID,))
            result = calculate_pace(rows, date_from, date_to, now)
        complete = bool(total and current == total and state and state[0])
        checked_at = state[1] if state else None
        age = (now-checked_at).total_seconds() if checked_at else None
        fresh = age is not None and 0 <= age <= 900
        return {'status': 'ok' if complete and fresh and not result['active_overlapping_bookings_without_valid_creation'] and not result['quality_issues'] else 'partial', 'property_id': PROPERTY_ID,
                'date_from': date_from, 'date_to_exclusive': date_to,
                'metric': 'creation_cohorts_of_currently_active_bookings',
                'coverage': {'summary_bookings': total, 'current_details': current,
                             'imported_dataset_complete': complete},
                'freshness': {'last_summary_check_at': checked_at, 'age_seconds': age, 'fresh': fresh},
                'limitations': [
                    'Current imported snapshot only; later cancellations and stay changes alter creation cohorts.',
                    'Cancellation times and historical occupancy snapshots are unavailable; net pickup is not calculated.',
                    'Booking counts are distinct bookings; room-night counts are per room stay per occupied night.',
                    'Missing creation timestamps are excluded and reported; counts then represent known observations only.',
                    'Naive creation timestamps are interpreted as Europe/Moscow. Repair blocks are excluded.'
                ], **result}
    except psycopg.Error:
        raise HTTPException(503, 'Database operation failed') from None
