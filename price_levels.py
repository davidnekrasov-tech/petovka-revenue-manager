"""Read-only, dated level-grid recommendations. Never writes to TravelLine."""
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from pricing import calculate_category_price
from tariff_pricing import RULES, round_tariff_price

GRID = json.loads(Path(__file__).with_name('price_levels_snapshot.json').read_text())


def level_source():
    return {k: GRID[k] for k in ('exported_at', 'source_sha256', 'date_from',
            'date_to_exclusive', 'calendar_verified_on', 'calendar_date_from',
            'calendar_date_to_exclusive', 'scope')} | {'automatically_updated': False}


def base_rows(night, category, level):
    index = (date.fromisoformat(night) - date.fromisoformat(GRID['date_from'])).days
    if not 0 <= index < GRID['days']:
        return {}
    rule = next((r for r in GRID['rules'] if r['level'] == level), None)
    if rule is None:
        return {}
    parent = next(p for p in GRID['tariffs'] if p['name'] == rule['parent'])
    config = parent['categories'].get(category, {})
    prices = {}
    # Adult main placements only. Child and extra-place changes need separate review.
    for label in ('Цена 1 осн.', 'Цена 2 осн.'):
        if label not in config:
            continue
        raw = next(v for end, v in GRID['series'][config[label]] if index < end)
        if raw is not None:
            value = Decimal(raw) - Decimal(rule['discount'])
            if value > 0:
                prices[label] = value
    return prices


def recommend_level(night, category, inventory, hotel_occupancy, now):
    current = GRID['calendar'].get(night, {}).get(category)
    reasons = list(inventory['withheld_reasons'])
    if current is None:
        reasons.append('level_calendar_missing')
    # A manual calendar read expires at the next Moscow date; booking refreshes
    # must never make this independent source appear fresh.
    if now.astimezone(ZoneInfo('Europe/Moscow')).date().isoformat() != GRID['calendar_verified_on']:
        reasons.append('level_calendar_stale')
    rows = base_rows(night, category, current)
    observed = GRID['observed_base_prices'].get(night, {}).get(category, {})
    if current is not None and (not rows or set(rows) != set(observed) or
            any(rows[k] != Decimal(observed[k]) for k in rows)):
        reasons.append('level_price_not_verified')
    selected = None
    factor = calculate_category_price(category, inventory['occupied'], hotel_occupancy)['multiplier']
    if not reasons:
        target = rows['Цена 1 осн.'] * Decimal(str(factor))
        candidates = [(r['level'], base_rows(night, category, r['level'])) for r in GRID['rules']]
        candidates = [(n, p) for n, p in candidates if set(p) == set(rows)]
        selected = min(candidates, key=lambda item: (
            abs(item[1]['Цена 1 осн.'] - target), item[0] != current,
            abs(item[1]['Цена 1 осн.'] - rows['Цена 1 осн.']), item[0]))[0]
    suggested = base_rows(night, category, selected) if selected else {}
    plans = []
    for name, (markup, meal) in RULES.items():
        placements = {}
        for label, base in rows.items():
            beds = 1 if label == 'Цена 1 осн.' else 2
            price = round_tariff_price(name, (base + beds * Decimal(meal)) * Decimal(markup))
            proposal = round_tariff_price(name, (suggested[label] + beds * Decimal(meal)) * Decimal(markup)) if selected else None
            placements[label] = {'current_price': format(price, '.2f'),
                'suggested_price': format(proposal, '.2f') if proposal is not None else None,
                'difference': format(proposal-price, '.2f') if proposal is not None else None,
                'withheld_reasons': list(reasons)}
        plans.append({'name': name, 'placements': placements})
    return {'current_level': current, 'recommended_level': selected,
            'current_base_prices': {k: format(v, '.2f') for k, v in rows.items()},
            'recommended_base_prices': {k: format(v, '.2f') for k, v in suggested.items()},
            'withheld_reasons': reasons, 'occupancy_multiplier': factor,
            'model': 'nearest_verified_grid_price_to_occupancy_target_v1',
            'tariffs': plans}
