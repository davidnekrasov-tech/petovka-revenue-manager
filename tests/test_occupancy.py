"""Offline regression tests: run with python -m unittest discover -s tests -v."""
import unittest
from datetime import date
from unittest.mock import patch
from occupancy_service import aggregate_stays, occupancy_diagnostic
from pricing import calculate_prices_from_occupancy


class OccupancyTests(unittest.TestCase):
    def test_stay_nights_and_categories(self):
        booking = {"status": "Active", "roomStays": [{
            "stayDates": {"arrivalDateTime": "2026-10-20T14:00:00",
                          "departureDateTime": "2026-10-22T12:00:00"},
            "roomType": {"name": "Комфорт с большой двуспальной кроватью"},
        }]}
        result = aggregate_stays([booking], date(2026, 10, 20), date(2026, 10, 23))
        self.assertEqual(set(result), {"2026-10-20", "2026-10-21"})
        self.assertEqual(result["2026-10-20"]["rooms"], 1)

    def test_duplicate_booking_is_not_double_counted(self):
        booking = {"number": "A-123", "status": "Active", "roomStays": [{
            "stayDates": {"arrivalDateTime": "2026-10-20",
                          "departureDateTime": "2026-10-21"},
            "roomType": {"name": "Стандарт"},
        }]}
        result = aggregate_stays([booking, booking], date(2026, 10, 20), date(2026, 10, 21))
        self.assertEqual(result["2026-10-20"]["rooms"], 1)

    def test_canceled_excluded(self):
        booking = {"status": "Canceled", "roomStays": [{
            "stayDates": {"arrivalDateTime": "2026-10-20", "departureDateTime": "2026-10-21"}
        }]}
        self.assertEqual(aggregate_stays([booking], date(2026, 10, 20), date(2026, 10, 21)), {})

    @patch("occupancy_service.time.sleep")
    @patch("occupancy_service._json_request")
    @patch.dict("os.environ", {"TRAVELLINE_CLIENT_ID": "test", "TRAVELLINE_CLIENT_SECRET": "test"})
    def test_pagination_and_partial_warning(self, request, sleep):
        request.side_effect = [
            {"access_token": "token"},
            {"bookingSummaries": [{"number": "1", "status": "Active"}],
             "hasMoreData": True, "continueToken": "next"},
            {"bookingSummaries": [{"number": "2", "status": "Active"}],
             "hasMoreData": False},
            {"booking": {"status": "Active", "roomStays": []}},
            {"booking": {"status": "Active", "roomStays": []}},
        ]
        result = occupancy_diagnostic("2026-10-20", "2026-10-21")
        self.assertEqual(result["summaries_scanned"], 2)
        self.assertEqual(result["details_loaded"], 2)
        self.assertFalse(result["safe_for_pricing"])
        self.assertFalse(result["complete"])
        self.assertIn("continueToken=next", request.call_args_list[2].args[0])


class PricingTests(unittest.TestCase):
    def test_manual_scenario(self):
        result = calculate_prices_from_occupancy(
            "2026-10-20", {"rooms": 5, "categories": {}}
        )
        self.assertEqual(result["occupied_rooms"], 5)
        self.assertEqual(result["available_rooms"], 10)


if __name__ == "__main__":
    unittest.main()
