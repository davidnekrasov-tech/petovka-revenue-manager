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
                    if not reasons:
                        # No rounding change when multiplier is 1. Round adjustments half up.
                        suggested=price if factor==1 else (price*Decimal(str(factor))/100).quantize(Decimal('1'),rounding=ROUND_HALF_UP)*100
                    placements[label]={
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
            results.append({'name':plan['name'],'currency':plan['currency'],'categories':categories})
        days.append({'date':day['date'],'occupied':day['occupied'],'capacity':day['capacity'],
                     'occupancy_percent':day['occupancy_percent'],'tariffs':results})
    return {'status':pricing['status'],'mode':'recommendations_only','source':source_info(),
            'automatically_updated':False,'freshness':pricing['freshness'],'coverage':pricing['coverage'],
            'quality_issues':pricing['quality_issues'],'withheld_reasons':pricing['withheld_reasons'],
            'limitations':[
                'Tariff prices and restrictions are a static export, not live TravelLine prices.',
                'Original meal/channel/discount distinctions are retained by tariff; inheritance formulas are unknown.',
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
