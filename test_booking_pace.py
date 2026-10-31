import unittest
from datetime import datetime, date, timezone
from copy import deepcopy
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from booking_pace import calculate_pace, created_at, router

NOW=datetime(2026,10,31,17,tzinfo=timezone.utc)
START=date(2026,11,1)
END=date(2026,11,3)

def booking(created='2026-10-31T15:00:00Z', status='Active'):
    return {'status':status,'createdDateTime':created,'currencyCode':'RUB','roomStays':[
        {'stayDates':{'arrivalDateTime':'2026-11-01T14:00','departureDateTime':'2026-11-03T12:00'},
         'roomType':{'name':'Комфорт'}}]}

class PaceTests(unittest.TestCase):
    def test_booking_and_room_nights_are_distinct(self):
        b=booking(); b['roomStays']*=2
        r=calculate_pace([(b,'Active')],START,END,NOW)
        self.assertEqual([w['currently_active_bookings_created'] for w in r['windows']],[1,1,1])
        self.assertEqual(r['windows'][0]['known_active_room_nights'],4)
        self.assertEqual([d['known_active_rooms_created'] for d in r['windows'][0]['dates']],[2,2])

    def test_exact_window_boundary_and_cancelled_excluded(self):
        rows=[(booking('2026-10-30T17:00:00Z'),'Active'),(booking(status='Cancelled'),'Cancelled')]
        r=calculate_pace(rows,START,END,NOW)
        self.assertEqual([w['currently_active_bookings_created'] for w in r['windows']],[0,1,1])
        self.assertIsNone(r['windows'][0]['net_pickup'])
        self.assertIsNone(r['windows'][0]['cancellations'])

    def test_unknown_creation_does_not_become_zero(self):
        r=calculate_pace([(booking(None),'Active')],START,END,NOW)
        self.assertEqual(r['active_overlapping_bookings_without_valid_creation'],1)
        self.assertIsNone(r['windows'][0]['currently_active_bookings_created'])
        self.assertEqual(r['windows'][0]['known_currently_active_bookings_created'],0)

    def test_timezone_future_and_checkout_exclusion(self):
        self.assertEqual(created_at('2026-10-31T20:00'),NOW)
        r=calculate_pace([(booking('2027-01-01'),'Active')],START,END,NOW)
        self.assertEqual(r['active_overlapping_bookings_without_valid_creation'],1)
        r=calculate_pace([(booking(),'Active')],date(2026,11,3),date(2026,11,4),NOW)
        self.assertEqual(r['windows'][0]['known_active_room_nights'],0)

    def test_auth_and_invalid_range_do_not_read_database(self):
        app=FastAPI(); app.include_router(router)
        with patch.dict('os.environ',{'SYNC_API_KEY':'test'}),TestClient(app) as c,patch('booking_pace.connect') as db:
            self.assertEqual(c.get('/api/storage/pace?date_from=2026-11-01&date_to=2026-11-03').status_code,401)
            self.assertEqual(c.get('/api/storage/pace?date_from=2026-11-01&date_to=2026-11-01',headers={'Authorization':'Bearer test'}).status_code,422)
            db.assert_not_called()

if __name__=='__main__': unittest.main()
