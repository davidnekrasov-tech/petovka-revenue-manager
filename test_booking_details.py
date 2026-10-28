import os
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from fastapi import FastAPI
from fastapi.testclient import TestClient

import booking_details as details


def sample(number="B1"):
    return {"booking": {
        "number": number, "status": "Active", "currencyCode": "RUB",
        "customer": {"email": "private@example.com"},
        "total": {"priceBeforeTax": 8550, "priceAfterTax": 8650},
        "roomStays": [{
            "stayDates": {"arrivalDateTime": "2026-10-28T14:00", "departureDateTime": "2026-10-29T12:00"},
            "roomType": {"id": "1", "name": "Standard"},
            "guests": [{"firstName": "PRIVATE"}],
            "dailyRates": [{"date": "2026-10-28", "priceBeforeTax": 8550, "ratePlanId": "2"}],
            "total": {"priceBeforeTax": 8550},
        }],
    }}


class DetailTests(unittest.TestCase):
    def setUp(self):
        details._shutdown.clear()

    def tearDown(self):
        details._shutdown.clear()

    def test_business_fields_and_rates_are_preserved_without_guest_contacts(self):
        result = details.select_details(sample(), "B1")
        self.assertNotIn("customer", result)
        self.assertNotIn("guests", result["roomStays"][0])
        self.assertEqual(result["roomStays"][0]["dailyRates"][0]["priceBeforeTax"], 8550)
        self.assertEqual(result["total"]["priceAfterTax"], 8650)

    def test_wrong_booking_number_is_rejected(self):
        with self.assertRaises(ValueError):
            details.select_details(sample("wrong"), "B1")

    def test_retry_after_seconds_date_and_fallback(self):
        now = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)
        self.assertEqual(details.retry_delay("300", now=now), 300)
        self.assertEqual(details.retry_delay("Wed, 28 Oct 2026 12:02:00 GMT", now=now), 120)
        self.assertEqual(details.retry_delay(None, attempt=2), 480)

    def test_new_routes_fail_closed(self):
        app = FastAPI()
        app.include_router(details.router)
        client = TestClient(app)
        with patch.dict(os.environ, {"SYNC_API_KEY": "test-secret"}), patch.object(details, "connect") as connection:
            self.assertEqual(client.post("/api/storage/details/start").status_code, 401)
            self.assertEqual(client.get("/api/storage/details/status").status_code, 401)
            self.assertEqual(client.post("/api/storage/details/pause").status_code, 401)
            connection.assert_not_called()

    def test_429_saves_future_retry_without_skipping_booking(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.side_effect = [("running", None), ("B1", "hash"), ("paused", None)]
        client = MagicMock()
        client.get_booking.side_effect = HTTPError("https://example.test", 429, "limit", {"Retry-After": "300"}, None)
        with patch.object(details, "set_job") as set_job, patch.object(details._shutdown, "wait"):
            details.process_job(conn, client)
        self.assertEqual(set_job.call_args.kwargs["error"], "HTTP_429")
        self.assertGreater((set_job.call_args.kwargs["retry_at"] - datetime.now(timezone.utc)).total_seconds(), 295)
        self.assertFalse(any("INSERT INTO tl_booking_details" in c.args[0] for c in conn.execute.call_args_list))

    def test_pause_does_not_request_travelline(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = ("paused", None)
        client = MagicMock()
        details.process_job(conn, client)
        client.get_booking.assert_not_called()

    def test_saved_booking_is_committed_before_next_iteration(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.side_effect = [("running", None), ("B1", "hash"), ("paused", None)]
        client = MagicMock()
        client.get_booking.return_value = sample()
        with patch.object(details._shutdown, "wait"):
            details.process_job(conn, client)
        self.assertEqual(conn.transaction.call_count, 1)
        self.assertTrue(any("INSERT INTO tl_booking_details" in c.args[0] for c in conn.execute.call_args_list))

    def test_token_is_cached_and_booking_number_is_escaped(self):
        client = details.TravelLineClient()
        token_response = MagicMock()
        token_response.__enter__.return_value.read.return_value = '{"access_token":"token","expires_in":900}'
        booking_response = MagicMock()
        booking_response.__enter__.return_value.read.return_value = '{"booking":{}}'
        with patch.dict(os.environ, {"TRAVELLINE_CLIENT_ID": "id", "TRAVELLINE_CLIENT_SECRET": "secret"}), patch.object(details, "urlopen", side_effect=[token_response, booking_response, booking_response]) as request:
            client.get_booking("B/1")
            client.get_booking("B/2")
        self.assertEqual(request.call_count, 3)
        self.assertTrue(request.call_args_list[1].args[0].full_url.endswith("B%2F1"))


if __name__ == "__main__":
    unittest.main()
