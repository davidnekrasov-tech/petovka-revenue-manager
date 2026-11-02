import unittest
from datetime import date, datetime, timezone, timedelta
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from weekly_report import build_report, router

NOW=datetime(2026,11,2,7,tzinfo=timezone.utc)
START=date(2026,11,2)
END=date(2026,11,9)
COVERAGE={'imported_dataset_complete':True,'summary_bookings':1,'current_details':1}
CATEGORY='Комфорт с большой двуспальной кроватью'

def records(created='2026-11-02T06:00:00Z'):
    return [({'status':'Active','createdDateTime':created,'currencyCode':'RUB','roomStays':[
        {'stayDates':{'arrivalDateTime':'2026-11-02T14:00','departureDateTime':'2026-11-04T12:00'},
         'roomType':{'name':CATEGORY},'dailyRates':[{'date':'2026-11-02','priceBeforeTax':6000},{'date':'2026-11-03','priceBeforeTax':6000}]}]},'Active')]

class ReportTests(unittest.TestCase):
    def test_combines_each_night_and_all_tariffs(self):
        r=build_report(records(),START,END,COVERAGE,NOW,NOW)
        self.assertEqual(r['status'],'ok')
        self.assertEqual(len(r['dates']),7)
        d=r['dates'][0]
        self.assertEqual(d['occupied'],1)
        self.assertEqual(d['new_active_rooms'],{'1':1,'3':1,'7':1})
        self.assertEqual(len(d['categories'][CATEGORY]['tariffs']),10)
        self.assertEqual(r['dates'][2]['occupied'],0)
        self.assertEqual(r['booking_pace']['windows'][0]['known_active_room_nights'],2)
        self.assertEqual(r['tariff_source']['exported_at'],'2026-11-02T09:26:00+03:00')

    def test_stale_and_future_check_withhold_prices(self):
        for checked in (NOW-timedelta(hours=1),NOW+timedelta(seconds=1),None):
            r=build_report(records(),START,END,COVERAGE,checked,NOW)
            self.assertFalse(r['freshness']['fresh'])
            self.assertFalse(r['booking_pace']['complete'])
            for p in r['dates'][0]['categories'][CATEGORY]['tariffs']:
                for placement in p['placements'].values():
                    self.assertIsNone(placement['suggested_price'])

    def test_unknown_creation_is_explicit_and_does_not_block_valid_occupancy(self):
        r=build_report(records(None),START,END,COVERAGE,NOW,NOW)
        self.assertEqual(r['status'],'needs_attention')
        self.assertEqual(r['dates'][0]['occupied'],1)
        self.assertFalse(r['dates'][0]['new_active_rooms_complete'])
        self.assertIsNone(r['booking_pace']['windows'][0]['currently_active_bookings_created'])

    def test_auth_and_range_before_database(self):
        app=FastAPI(); app.include_router(router)
        with patch.dict('os.environ',{'SYNC_API_KEY':'test'}),TestClient(app) as c,patch('weekly_report.connect') as db:
            self.assertEqual(c.get('/api/storage/report').status_code,401)
            self.assertEqual(c.get('/api/storage/report?nights=32',headers={'Authorization':'Bearer test'}).status_code,422)
            db.assert_not_called()

if __name__=='__main__': unittest.main()
