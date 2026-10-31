"""Compare each exported tariff separately with occupancy-based suggestions."""
import json
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException

from booking_storage import authorize
from database_pricing import pricing_from_database
from pricing import calculate_category_price

SNAPSHOT=json.loads(Path(__file__).with_name('tariff_snapshot.json').read_text())
router=APIRouter(prefix='/api/storage',tags=['Tariffs from export'],dependencies=[Depends(authorize)])

# Read from the hotel's inheritance settings on 2026-10-31.
# Each rule uses «Базовый без завтрака». Meal supplement precedes markup.
RULES = {
    'Тариф с надбавкой для ОТА': ('1.18', '0'),
    'Скидка 10% для постоянных гостей': ('0.90', '0'),
    'Скидка 15% для постоянных гостей': ('0.85', '0'),
    'Длительное проживание': ('0.93', '0'),
    'Тариф с завтраком для OTA': ('1.18', '900'),
    'Продли выходные со скидкой 20%!': ('0.85', '0'),
    'Тариф без завтрака для ЯП': ('1.25', '0'),
    'Тариф с завтраком для ЯП': ('1.25', '900'),
    'Лучшая цена дня без завтрака!': ('1.05', '0'),
    'Лучшая цена дня с завтраком!': ('1.05', '900'),
}
ANCHOR = 'Тариф с надбавкой для ОТА'


def linked_price(plan_name, category, night, label, price, factor):
    """Recover one shared room base; never discount the meal component.

    Validate the observed adult placement against the rule before applying it:
    overrides or rules not covering a placement must not silently get repriced.
    """
    rule = RULES.get(plan_name)
    if rule is None:
        return None, None, 'unverified_inheritance_rule'
    anchor = next(p for p in SNAPSHOT['tariffs'] if p['name'] == ANCHOR)
    anchor_rows = exported_rows(anchor['categories'][category], night)
    raw = anchor_rows.get(label) if anchor_rows else None
    if raw is None or Decimal(raw) <= 0:
        return None, None, 'missing_parent_price_basis'
    base = (Decimal(raw) / Decimal('1.18')).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    multiplier, meal = map(Decimal, rule)
    beds = 1 if label == 'Цена 1 осн.' else 2
    expected = ((base + beds * meal) * multiplier).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    if abs(expected - price) > Decimal('.02'):
        return None, base, 'export_does_not_match_inheritance_rule'
    adjusted = base if factor == 1 else (base * Decimal(str(factor)) / 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * 100
    suggested = price if factor == 1 else ((adjusted + beds * meal) * multiplier).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    return suggested, base, None


def source_info():
    return {k:SNAPSHOT[k] for k in ('property_id','exported_at','date_from','date_to_exclusive','source_sha256')}


def exported_rows(config, night):
    index=(date.fromisoformat(night)-date.fromisoformat(SNAPSHOT['date_from'])).days
    if not 0 <= index < SNAPSHOT['days']:
        return None
    result={}
    for label,series_id in config.items():
        result[label]=next(value for end,value in SNAPSHOT['series'][series_id] if index<end)
    return result


@router.get('/tariffs')
def tariffs():
    return {'status':'ok','source':source_info(),'automatically_updated':False,
            'tariff_count':len(SNAPSHOT['tariffs']),
            'tariffs':[{'name':p['name'],'currency':p['currency'],'categories':list(p['categories'])} for p in SNAPSHOT['tariffs']]}


def compare_tariffs(pricing, tariff_name=None):
    plans=[p for p in SNAPSHOT['tariffs'] if tariff_name is None or p['name']==tariff_name]
    if not plans:raise HTTPException(404,'Tariff name is not in the export')
    days=[]
    for day in pricing['dates']:
        results=[]
        for plan in plans:
            categories={}
            for name,observed in day['categories'].items():
                rows=exported_rows(plan['categories'][name],day['date'])
                restrictions=[]
                if rows is None:restrictions.append('date_outside_export')
                elif rows.get('Close/Open') is not None:restrictions.append('exported_close_marker')
                factor=calculate_category_price(name,observed['occupied'],day['occupancy_percent'])['multiplier']
                placements={}
                for label in ('Цена 1 осн.','Цена 2 осн.'):
                    if label not in plan['categories'][name]:continue
                    raw=rows.get(label) if rows else None
                    price=Decimal(raw) if raw is not None else None
                    reasons=list(observed['withheld_reasons'])+restrictions
                    if price is None:reasons.append('missing_exported_price')
                    elif price<=0:reasons.append('non_positive_exported_price')
                    suggested=None
                    parent_base=None
                    if not reasons:
                        suggested,parent_base,rule_error=linked_price(plan['name'],name,day['date'],label,price,factor)
                        if rule_error:reasons.append(rule_error)
                    placements[label]={
                        'parent_base_price':format(parent_base,'.2f') if parent_base is not None else None,
                        'exported_price':format(price,'.2f') if price is not None else None,
                        'suggested_price':format(suggested,'.2f') if suggested is not None else None,
                        'difference':format(suggested-price,'.2f') if suggested is not None else None,
                        'change_percent':float(((suggested/price-1)*100).quantize(Decimal('.1'))) if suggested is not None else None,
                        'withheld_reasons':reasons,
                    }
                categories[name]={
                    'occupied':observed['occupied'],'capacity':observed['capacity'],'available':observed['available'],
                    'occupancy_percent':observed['occupancy_percent'],'occupancy_multiplier':factor,
                    'placements':placements,'exported_rows':rows,
                }
            rule=RULES.get(plan['name'])
            results.append({'name':plan['name'],'currency':plan['currency'],
                            'inheritance':{'parent':'Базовый без завтрака','multiplier':rule[0],
                                           'meal_per_place':rule[1],'verified_on':'2026-10-31'} if rule else None,
                            'categories':categories})
        days.append({'date':day['date'],'occupied':day['occupied'],'capacity':day['capacity'],
                     'occupancy_percent':day['occupancy_percent'],'tariffs':results})
    return {'status':pricing['status'],'mode':'recommendations_only','source':source_info(),
            'automatically_updated':False,'freshness':pricing['freshness'],'coverage':pricing['coverage'],
            'quality_issues':pricing['quality_issues'],'withheld_reasons':pricing['withheld_reasons'],
            'limitations':[
                'Tariff prices and restrictions are a static export, not live TravelLine prices.',
                'Inheritance rules were read from TravelLine on 2026-10-31; they are not refreshed automatically.',
                'The shared parent price is reconstructed from the exported OTA tariff, not read live. Rule mismatches withhold suggestions.',
                'Only the room base is adjusted and rounded to hundreds; meal supplements and tariff multipliers are then applied, rounded to kopecks.',
                'The weekend offer name says 20%, but its configured inheritance discount is 15%.',
                'Child prices are retained unchanged; no child-price suggestions are calculated.',
                'A blank Close/Open cell does not certify that a rate is bookable; MinLOS and other booking conditions need review.',
                'Repair blocks are excluded; recommendations require review and are never published automatically.'
            ],'dates':days}


@router.get('/pricing/tariffs')
def pricing_tariffs(date_from:date,date_to:date,tariff_name:str|None=None):
    """All exported tariffs by default. Dates checkout-exclusive; optional exact tariff name."""
    if not 1 <= (date_to-date_from).days <= 31:
        raise HTTPException(422,'Tariff comparison range must contain 1 to 31 nights')
    if tariff_name is not None and tariff_name not in {p['name'] for p in SNAPSHOT['tariffs']}:
        raise HTTPException(404,'Tariff name is not in the export')
    return compare_tariffs(pricing_from_database(date_from,date_to),tariff_name)
