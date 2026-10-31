"""Read-only, occupancy-based price suggestions from imported booking snapshots."""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import psycopg
from fastapi import APIRouter, Depends, HTTPException

from booking_storage import PROPERTY_ID, authorize, connect
from occupancy import occupancy
from pricing import ROOM_CATEGORIES, calculate_category_price

MAX_AGE_SECONDS = 900
router = APIRouter(prefix='/api/storage', tags=['Pricing from database'], dependencies=[Depends(authorize)])


def build_recommendations(snapshot, checked_at, now=None):
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(ZoneInfo('Europe/Moscow')).date()
    age = max(0, (now - checked_at).total_seconds()) if checked_at else None
    blockers = []
    if not snapshot['coverage']['imported_dataset_complete']:
        blockers.append('incomplete_booking_snapshots')
    if age is None or age > MAX_AGE_SECONDS:
        blockers.append('summary_check_missing_or_stale')
    if snapshot.get('quality_issues'):
        blockers.append('occupancy_quality_issues')
    dates = []
    for day in snapshot['dates']:
        day_blockers = list(blockers)
        if date.fromisoformat(day['date']) < today:
            day_blockers.append('past_date')
        if day.get('unknown_categories') or day.get('over_capacity'):
            day_blockers.append('invalid_inventory')
        categories = {}
        for name, config in ROOM_CATEGORIES.items():
            observed = day['categories'][name]
            reasons = list(day_blockers)
            if observed['over_capacity']:
                reasons.append('category_over_capacity')
            sold_out = observed['available'] == 0
            if sold_out:
                reasons.append('sold_out')
            calculation = calculate_category_price(name, observed['occupied'], day['occupancy_percent'])
            allowed = not reasons
            categories[name] = {
                'capacity':observed['capacity'], 'occupied':observed['occupied'],
                'available':observed['available'], 'occupancy_percent':observed['occupancy_percent'],
                'base_price':config['base_price'],
                'recommended_price':calculation['recommended_price'] if allowed else None,
                'price_change_percent':calculation['price_change_percent'] if allowed else None,
                'action':'review_price' if allowed else ('sold_out' if sold_out and not day_blockers else 'withheld'),
                'reason':calculation['recommendation'] if allowed else None,
                'withheld_reasons':reasons,
            }
        dates.append({'date':day['date'], 'capacity':day['capacity'], 'occupied':day['occupied'],
                      'available':day['available'], 'occupancy_percent':day['occupancy_percent'],
                      'categories':categories})
    return {
        'status':'ok' if not blockers else 'needs_attention', 'property_id':PROPERTY_ID,
        'date_from':snapshot['date_from'], 'date_to_exclusive':snapshot['date_to_exclusive'],
        'currency':'RUB', 'mode':'recommendations_only',
        'model':'existing_occupancy_rules_v1',
        'base_price_source':'Configured reference prices in pricing.py; not current TravelLine tariffs',
        'repair_blocks_included':False,
        'limitations':['Repair blocks are excluded; capacity remains 15 rooms.',
                       'Reference prices require hotel approval before operational use.',
                       'Competitors, booking pace, lead time and events are not included.'],
        'freshness':{'generated_at':now, 'last_summary_check_at':checked_at,
                     'summary_check_age_seconds':round(age, 1) if age is not None else None,
                     'max_age_seconds':MAX_AGE_SECONDS},
        'coverage':snapshot['coverage'], 'quality_issues':snapshot.get('quality_issues', {}),
        'withheld_reasons':blockers, 'dates':dates,
    }


@router.get('/pricing')
def pricing_from_database(date_from: date, date_to: date):
    """One reference price per room/night; checkout exclusive. Never writes to TravelLine."""
    if not 1 <= (date_to - date_from).days <= 90:
        raise HTTPException(422, 'Pricing range must contain 1 to 90 nights')
    try:
        # Capture freshness before loading occupancy: a concurrent later poll must
        # not make an earlier occupancy snapshot look fresher than it is.
        with connect() as conn:
            conn.execute('SET TRANSACTION READ ONLY')
            exists = conn.execute("SELECT to_regclass('public.tl_sync_state')").fetchone()[0]
            if not exists:
                raise HTTPException(409, 'Import booking summaries and details first')
            row = conn.execute('SELECT updated_at FROM tl_sync_state WHERE property_id = %s', (PROPERTY_ID,)).fetchone()
            checked_at = row[0] if row else None
        snapshot = occupancy(date_from, date_to)
        return build_recommendations(snapshot, checked_at)
    except psycopg.Error:
        raise HTTPException(503, 'Database operation failed') from None
