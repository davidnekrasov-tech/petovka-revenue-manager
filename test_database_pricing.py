import copy
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from occupancy import calculate_occupancy
from database_pricing import build_recommendations, router
from pricing import ROOM_CATEGORIES

NOW = datetime(2026, 10, 31, 8, tzinfo=timezone.utc)


def snapshot():
    records=[]
    for name, count in zip(ROOM_CATEGORIES, (2,2,3,2)):
        for _ in range(count):
            records.append(({'status':'Active', 'currencyCode':'RUB', 'roomStays':[{
                'roomType':{'name':name},
                'stayDates':{'arrivalDateTime':'2026-10-31T14:00','departureDateTime':'2026-11-01T12:00'},
                'dailyRates':[],
            }]}, 'Active'))
    return {'date_from':date(2026,10,31), 'date_to_exclusive':date(2026,11,1),
            'coverage':{'imported_dataset_complete':True},
            **calculate_occupancy(records,date(2026,10,31),date(2026,11,1))}


class DatabasePricingTests(unittest.TestCase):
    def test_real_category_counts_and_reference_prices(self):
        result=build_recommendations(snapshot(), NOW, NOW)
        day=result['dates'][0]
        self.assertEqual((day['occupied'],day['capacity'],day['occupancy_percent']), (9,15,60))
        cats=list(day['categories'].values())
        self.assertEqual([c['recommended_price'] for c in cats], [None,None,6500,7500])
        self.assertEqual([c['base_price'] for c in cats], [5000,5500,6500,7500])
        self.assertEqual(cats[0]['action'],'sold_out')
        self.assertFalse(result['repair_blocks_included'])

    def test_incomplete_snapshots_withhold_all_prices(self):
        data=snapshot();data['coverage']['imported_dataset_complete']=False
        result=build_recommendations(data,NOW,NOW)
        self.assertEqual(result['status'],'needs_attention')
        self.assertTrue(all(c['recommended_price'] is None for c in result['dates'][0]['categories'].values()))

    def test_stale_check_not_changed_booking_timestamp_controls_freshness(self):
        for check in (None,NOW-timedelta(seconds=901)):
            result=build_recommendations(snapshot(),check,NOW)
            self.assertIn('summary_check_missing_or_stale',result['withheld_reasons'])
        result=build_recommendations(snapshot(),NOW-timedelta(seconds=300),NOW)
        self.assertEqual(result['status'],'ok')

    def test_past_dates_are_withheld_using_moscow_calendar(self):
        result=build_recommendations(snapshot(),NOW,datetime(2026,10,31,22,tzinfo=timezone.utc))
        self.assertIn('past_date',list(result['dates'][0]['categories'].values())[2]['withheld_reasons'])

    def test_unknown_or_over_capacity_never_produces_price(self):
        for issue in ('unknown_room_category','inventory_exceeded'):
            data=snapshot();data['quality_issues']={issue:1}
            result=build_recommendations(data,NOW,NOW)
            self.assertIn('occupancy_quality_issues',result['withheld_reasons'])
            self.assertIsNone(list(result['dates'][0]['categories'].values())[2]['recommended_price'])

    def test_missing_booked_amounts_do_not_block_occupancy_rules(self):
        result=build_recommendations(snapshot(),NOW,NOW)
        self.assertEqual(list(result['dates'][0]['categories'].values())[2]['recommended_price'],6500)

    def test_no_snapshot_mutation(self):
        data=snapshot();before=copy.deepcopy(data)
        build_recommendations(data,NOW,NOW)
        self.assertEqual(data,before)

    def test_endpoint_is_protected_and_validates_range_before_database(self):
        app=FastAPI();app.include_router(router)
        with patch.dict('os.environ',{'SYNC_API_KEY':'test'}),TestClient(app) as c:
            with patch('database_pricing.connect') as conn:
                self.assertEqual(c.get('/api/storage/pricing?date_from=2026-10-31&date_to=2026-11-01').status_code,401)
                response=c.get('/api/storage/pricing?date_from=2026-10-31&date_to=2026-10-31',headers={'Authorization':'Bearer test'})
                self.assertEqual(response.status_code,422)
                conn.assert_not_called()

    def test_endpoint_uses_read_only_freshness_and_occupancy_reader(self):
        from database_pricing import pricing_from_database
        conn=MagicMock();conn.__enter__.return_value=conn
        conn.execute.return_value.fetchone.side_effect=[('tl_sync_state',),(NOW,)]
        with patch('database_pricing.connect',return_value=conn),patch('database_pricing.occupancy',return_value=snapshot()) as read,patch('database_pricing.build_recommendations',return_value={'status':'ok'}) as build:
            pricing_from_database(date(2026,10,31),date(2026,11,1))
        read.assert_called_once_with(date(2026,10,31),date(2026,11,1))
        build.assert_called_once_with(snapshot(),NOW)
        self.assertIn('READ ONLY',conn.execute.call_args_list[0].args[0])


if __name__=='__main__': unittest.main()
