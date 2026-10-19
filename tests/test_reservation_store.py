import sqlite3
import unittest
from reservation_store import init_db, upsert_booking, calendar


def booking(number="123", status="Active", arrival="2026-10-20", departure="2026-10-22"):
    return {"number": number, "status": status, "guest": {"name": "SHOULD_NOT_BE_STORED"},
            "roomStays": [{"stayDates": {"arrivalDateTime": arrival, "departureDateTime": departure},
                           "roomType": {"name": "Стандарт"}}]}


class ReservationStoreTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        init_db(self.db)

    def tearDown(self):
        self.db.close()

    def test_upsert_does_not_duplicate(self):
        upsert_booking(self.db, booking())
        upsert_booking(self.db, booking())
        result = calendar(self.db, "2026-10-20", days=3)
        self.assertEqual(result["days"]["2026-10-20"]["occupied_rooms"], 1)
        self.assertEqual(result["days"]["2026-10-22"]["occupied_rooms"], 0)
        self.assertIsNone(result["days"]["2026-10-22"]["available_rooms"])

    def test_cancel_removes_room_nights(self):
        upsert_booking(self.db, booking())
        upsert_booking(self.db, booking(status="Canceled"))
        self.assertEqual(calendar(self.db, "2026-10-20", days=1)["days"]["2026-10-20"]["occupied_rooms"], 0)

    def test_date_change_replaces_stay(self):
        upsert_booking(self.db, booking())
        upsert_booking(self.db, booking(arrival="2026-10-23", departure="2026-10-24"))
        result = calendar(self.db, "2026-10-20", days=5)["days"]
        self.assertEqual(result["2026-10-20"]["occupied_rooms"], 0)
        self.assertEqual(result["2026-10-23"]["occupied_rooms"], 1)

    def test_does_not_store_guest_pii(self):
        upsert_booking(self.db, booking())
        row = self.db.execute("SELECT stays_json FROM reservation_state").fetchone()[0]
        self.assertNotIn("SHOULD_NOT_BE_STORED", row)

    def test_calendar_is_not_authoritative(self):
        result = calendar(self.db, "2026-10-20", days=90)
        self.assertFalse(result["safe_for_pricing"])
        self.assertFalse(result["complete"])
        self.assertEqual(len(result["days"]), 90)


if __name__ == "__main__":
    unittest.main()
