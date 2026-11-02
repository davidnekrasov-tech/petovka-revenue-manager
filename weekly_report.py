"""One read-only database snapshot for occupancy, creation cohorts and tariffs."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from booking_storage import PROPERTY_ID, authorize, connect
from booking_pace import calculate_pace
from occupancy import calculate_occupancy
from database_pricing import build_recommendations
from tariff_pricing import compare_tariffs
from price_levels import level_source, recommend_level

router = APIRouter(prefix='/api/storage', tags=['Weekly report'], dependencies=[Depends(authorize)])


def build_report(records, date_from, date_to, coverage, checked_at, now):
    snapshot = {'date_from': date_from, 'date_to_exclusive': date_to,
                'coverage': coverage, **calculate_occupancy(records, date_from, date_to)}
    pricing = build_recommendations(snapshot, checked_at, now)
    age = (now-checked_at).total_seconds() if checked_at else None
    # A future timestamp must not certify a fresh report.
    if age is not None and age < 0:
        pricing = build_recommendations(snapshot, None, now)
    comparisons = compare_tariffs(pricing)
    pace = calculate_pace(records, date_from, date_to, now)
    pace_complete = (coverage['imported_dataset_complete'] and age is not None
                     and 0 <= age <= 900
                     and not pace['active_overlapping_bookings_without_valid_creation']
                     and not pace['quality_issues']
                     and not any(w['quality_issues'] for w in pace['windows']))
    cohort_dates = {w['days']: {d['date']: d for d in w['dates']} for w in pace['windows']}
    days = []
    for observed, compared, suggested in zip(snapshot['dates'], comparisons['dates'], pricing['dates']):
        categories = {}
        for name, category in observed['categories'].items():
            categories[name] = {
                **category,
                'new_active_rooms': {str(n): cohort_dates[n][observed['date']]['categories'][name]
                                     for n in (1, 3, 7)},
                'new_active_rooms_complete': pace_complete,
                'reason': suggested['categories'][name]['reason'],
                'withheld_reasons': suggested['categories'][name]['withheld_reasons'],
                'price_levels': recommend_level(observed['date'], name,
                    suggested['categories'][name], observed['occupancy_percent'], now),
                'tariffs': [{'name': p['name'], 'currency': p['currency'],
                             'placements': p['categories'][name]['placements'],
                             'exported_rows': p['categories'][name]['exported_rows']}
                            for p in compared['tariffs']],
            }
        days.append({k: v for k, v in observed.items() if k != 'categories'} | {
            'new_active_rooms': {str(n): cohort_dates[n][observed['date']]['known_active_rooms_created']
                                 for n in (1, 3, 7)},
            'new_active_rooms_complete': pace_complete, 'categories': categories})
    return {
        'status': 'ok' if pricing['status'] == 'ok' and pace_complete else 'needs_attention',
        'property_id': PROPERTY_ID, 'date_from': date_from, 'date_to_exclusive': date_to,
        'generated_at': now, 'mode': 'recommendations_only',
        'database_consistency': 'single_repeatable_read_snapshot',
        'currency': 'RUB', 'repair_blocks_included': False,
        'tariff_source': comparisons['source'], 'tariffs_automatically_updated': False,
        'price_level_source': level_source(),
        'freshness': {'last_summary_check_at': checked_at, 'age_seconds': age,
                      'fresh': age is not None and 0 <= age <= 900},
        'coverage': coverage, 'quality_issues': snapshot['quality_issues'],
        'withheld_reasons': pricing['withheld_reasons'],
        'booking_pace': {'metric': 'creation_cohorts_of_currently_active_bookings',
                         'complete': pace_complete,
                         'active_bookings_without_valid_creation': pace['active_overlapping_bookings_without_valid_creation'],
                         'quality_issues': pace['quality_issues'],
                         'windows': [{k: v for k, v in w.items() if k != 'dates'} for w in pace['windows']]},
        'limitations': comparisons['limitations'] + [
            'Price-level calendar is a manual dated snapshot. Level suggestions expire after its Moscow verification date and are withheld outside verified dates.',
            'Level recommendations choose the closest grid price to the existing occupancy target, using one adult as the anchor. They do not assess competitors or demand forecasts.',
            'Pace windows are nested rolling 24/72/168 hours. Counts cover currently active bookings only, not net pickup.',
            'Booking pace is displayed as context and does not change the occupancy pricing formula.',
            'Exported tariffs have their own timestamp; fresh booking synchronization does not refresh tariff prices.',
            'Known creation counts remain visible when incomplete; consult booking_pace.complete before use.',
        ],
        'dates': days,
    }


@router.get('/report')
def weekly_report(date_from: date | None = None, nights: int = 7):
    """Read-only report. Defaults to seven nights from today in Europe/Moscow."""
    if not 1 <= nights <= 31:
        raise HTTPException(422, 'nights must be between 1 and 31')
    now = datetime.now(timezone.utc)
    date_from = date_from or now.astimezone(ZoneInfo('Europe/Moscow')).date()
    date_to = date_from + timedelta(days=nights)
    try:
        with connect() as connection:
            connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            tables = connection.execute("SELECT to_regclass('public.tl_booking_summaries'), to_regclass('public.tl_booking_details'), to_regclass('public.tl_sync_state')").fetchone()
            if any(t is None for t in tables):
                raise HTTPException(409, 'Import booking summaries and details first')
            total, current, summary_at, detail_at = connection.execute('''
                SELECT count(*), count(d.booking_number), max(s.synced_at), max(d.synced_at)
                FROM tl_booking_summaries s LEFT JOIN tl_booking_details d
                ON d.property_id=s.property_id AND d.booking_number=s.booking_number
                AND d.source_hash=md5(s.payload::text) WHERE s.property_id=%s
            ''', (PROPERTY_ID,)).fetchone()
            state = connection.execute('SELECT completed, updated_at FROM tl_sync_state WHERE property_id=%s', (PROPERTY_ID,)).fetchone()
            records = connection.execute('''SELECT d.payload, s.payload->>'status'
                FROM tl_booking_summaries s JOIN tl_booking_details d USING (property_id, booking_number)
                WHERE s.property_id=%s AND d.source_hash=md5(s.payload::text)
            ''', (PROPERTY_ID,)).fetchall()
        coverage = {'summary_bookings': total, 'current_details': current,
                    'missing_or_stale_details': total-current,
                    'summary_import_completed': bool(state and state[0]),
                    'imported_dataset_complete': bool(total and total == current and state and state[0]),
                    'last_summary_import_at': summary_at, 'last_detail_import_at': detail_at}
        return build_report(records, date_from, date_to, coverage, state[1] if state else None, now)
    except psycopg.Error:
        raise HTTPException(503, 'Database operation failed') from None
