import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from occupancy import calculate_occupancy, router


START = date(2026, 10, 30)
END = date(2026, 11, 2)


def booking(arrival="2026-10-30T14:00", departure="2026-11-02T12:00", category="Комфорт", currency="RUB"):
    return {"status": "Active", "currencyCode": currency, "roomStays": [{
        "stayDates": {"arrivalDateTime": arrival, "departureDateTime": departure},
        "roomType": {"name": category},
        "dailyRates": [{"date": "2026-10-30T00:00:00", "priceBeforeTax": 5000.10},
                       {"date": "2026-10-31", "priceBeforeTax": 6000.20},
                       {"date": "2026-11-01", "priceBeforeTax": 7000.30}],
    }]}


class OccupancyTests(unittest.TestCase):
    def calculate(self, *records):
        return calculate_occupancy(records, START, END)

    def test_three_nights_and_exact_daily_prices(self):
        days = self.calculate((booking(), "Active"))["dates"]
        self.assertEqual([d["date"] for d in days], ["2026-10-30", "2026-10-31", "2026-11-01"])
        self.assertEqual([d["occupied"] for d in days], [1, 1, 1])
        self.assertEqual([d["room_amount_before_tax"] for d in days], ["5000.10", "6000.20", "7000.30"])
        comfort = days[0]["categories"]["Комфорт с большой двуспальной кроватью"]
        self.assertEqual((comfort["capacity"], comfort["available"], comfort["occupancy_percent"]), (5, 4, 20))

    def test_checkout_excluded_and_hotel_local_date_preserved(self):
        days = self.calculate((booking(arrival="2026-10-30T00:30+03:00", departure="2026-10-31T12:00+03:00"), "Active"))["dates"]
        self.assertEqual([d["occupied"] for d in days], [1, 0, 0])

    def test_cancelled_summary_or_detail_excluded(self):
        cancelled = booking()
        cancelled["status"] = "Cancelled"
        days = self.calculate((booking(), "Cancelled"), (cancelled, "Active"))["dates"]
        self.assertEqual([d["occupied"] for d in days], [0, 0, 0])

    def test_multiple_stays_count_as_multiple_rooms(self):
        record = booking()
        record["roomStays"].append(booking(category="Стандарт")["roomStays"][0])
        day = self.calculate((record, "Active"))["dates"][0]
        self.assertEqual(day["occupied"], 2)
        self.assertEqual(day["room_amount_before_tax"], "10000.20")

    def test_missing_price_is_not_reported_as_zero_or_allocated_total(self):
        record = booking()
        record["roomStays"][0]["dailyRates"] = []
        record["total"] = {"priceBeforeTax": 99999}
        day = self.calculate((record, "Active"))["dates"][0]
        self.assertEqual(day["occupied"], 1)
        self.assertIsNone(day["room_amount_before_tax"])
        self.assertEqual(day["missing_price_room_nights"], 1)

    def test_currency_is_not_summed_into_rubles(self):
        day = self.calculate((booking(currency="EUR"), "Active"))["dates"][0]
        self.assertIsNone(day["room_amount_before_tax"])

    def test_unknown_category_is_counted_in_total_and_flagged(self):
        result = self.calculate((booking(category="Unknown"), "Active"))
        day = result["dates"][0]
        self.assertEqual(day["occupied"], 1)
        self.assertEqual(day["unknown_categories"], {"Unknown": 1})
        self.assertIn("unknown_room_category", result["quality_issues"])

    def test_overbooking_is_visible_and_not_clamped(self):
        result = self.calculate(*[(booking(), "Active")] * 16)
        day = result["dates"][0]
        self.assertEqual(day["occupied"], 16)
        self.assertEqual(day["over_capacity"], 1)
        self.assertEqual(day["categories"]["Комфорт с большой двуспальной кроватью"]["over_capacity"], 11)
        self.assertIn("inventory_exceeded", result["quality_issues"])

    def test_duplicate_price_is_ambiguous(self):
        record = booking()
        rates = record["roomStays"][0]["dailyRates"]
        rates.append(rates[0].copy())
        day = self.calculate((record, "Active"))["dates"][0]
        self.assertIsNone(day["room_amount_before_tax"])

    def test_day_use_and_outside_range_do_not_count(self):
        days = self.calculate(
            (booking(departure="2026-10-30T18:00"), "Active"),
            (booking(arrival="2026-11-02T14:00", departure="2026-11-03T12:00"), "Active"),
        )["dates"]
        self.assertEqual([d["occupied"] for d in days], [0, 0, 0])

    def test_endpoint_requires_key_and_valid_range_before_database(self):
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        with patch.dict("os.environ", {"SYNC_API_KEY": "test"}), patch("occupancy.connect") as connection:
            self.assertEqual(client.get("/api/storage/occupancy?date_from=2026-10-30&date_to=2026-11-02").status_code, 401)
            response = client.get("/api/storage/occupancy?date_from=2026-11-02&date_to=2026-10-30", headers={"Authorization": "Bearer test"})
            self.assertEqual(response.status_code, 422)
            connection.assert_not_called()

    def test_endpoint_marks_stale_details_and_uses_read_only_snapshot(self):
        app = FastAPI()
        app.include_router(router)
        connection = MagicMock()
        connection.__enter__.return_value = connection
        tables = MagicMock()
        tables.fetchone.return_value = ("summaries", "details", "state")
        coverage = MagicMock()
        coverage.fetchone.return_value = (2, 1, None, None)
        state = MagicMock()
        state.fetchone.return_value = (True,)
        connection.execute.side_effect = [None, tables, coverage, state, [(booking(), "Active")]]
        with patch.dict("os.environ", {"SYNC_API_KEY": "test"}), patch("occupancy.connect", return_value=connection):
            response = TestClient(app).get(
                "/api/storage/occupancy?date_from=2026-10-30&date_to=2026-11-02",
                headers={"Authorization": "Bearer test"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["coverage"]["imported_dataset_complete"])
        self.assertEqual(response.json()["coverage"]["missing_or_stale_details"], 1)
        self.assertIn("REPEATABLE READ READ ONLY", connection.execute.call_args_list[0].args[0])
        self.assertIn("d.source_hash = md5(s.payload::text)", connection.execute.call_args_list[-1].args[0])


if __name__ == "__main__":
    unittest.main()
