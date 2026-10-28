import unittest
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from booking_storage import validate_page
from reconciliation import audit_stays, fetch_changes, validate_changes, update_summaries


class ReconciliationTests(unittest.TestCase):
    def test_final_cursor_is_preserved_for_later_polling(self):
        page = {"status": "ok", "bookings": [], "has_more_data": False, "continue_token": "final"}
        self.assertEqual(validate_page(page, "old"), ([], False, "final"))
        self.assertEqual(validate_changes(page, "final"), ([], False, "final"))

    def test_missing_final_update_cursor_is_rejected(self):
        with self.assertRaises(HTTPException):
            validate_changes({"status": "ok", "bookings": [], "has_more_data": False}, None)

    def test_fallback_uses_two_day_overlap_and_no_continue_token(self):
        auth, data = MagicMock(), MagicMock()
        auth.__enter__.return_value.read.return_value = '{"access_token":"test"}'
        data.__enter__.return_value.read.return_value = '{"bookingSummaries":[],"hasMoreData":false,"continueToken":"cursor"}'
        with patch.dict("os.environ", {"TRAVELLINE_CLIENT_ID": "id", "TRAVELLINE_CLIENT_SECRET": "secret"}), patch("reconciliation.urlopen", side_effect=[auth, data]) as request:
            fetch_changes(None, datetime(2026, 10, 28, 10, 30, tzinfo=timezone.utc))
        url = request.call_args.args[0].full_url
        self.assertIn("lastModification=2026-10-26", url)
        self.assertNotIn("continueToken", url)

    def test_audit_explains_cancelled_stale_and_included_stays_without_guest_names(self):
        payload = {"status": "Active", "customer": {"name": "PRIVATE"}, "roomStays": [{
            "stayDates": {"arrivalDateTime": "2026-10-30T14:00", "departureDateTime": "2026-11-01T12:00"},
            "roomType": {"name": "Стандарт"},
        }]}
        rows = [("B1", "Active", payload, True, None), ("B2", "Cancelled", payload, True, None), ("B3", "Active", payload, False, None)]
        result = audit_stays(rows, date(2026, 10, 30), date(2026, 11, 2))
        self.assertEqual([s["calculation_reason"] for s in result["stays"]], ["included", "cancelled", "stale_details"])
        self.assertEqual(result["stays"][0]["nights"], ["2026-10-30", "2026-10-31"])
        self.assertNotIn("PRIVATE", str(result))

    def test_updates_commit_changed_summaries_and_final_cursor(self):
        conn = MagicMock()
        conn.__enter__.return_value = conn
        conn.execute.return_value.fetchone.side_effect = [(True,), (None, datetime(2026, 10, 28, tzinfo=timezone.utc), 88), ("B1",)]
        page = {"status": "ok", "bookings": [{"number": "B1", "status": "Active"}], "has_more_data": False, "continue_token": "final"}
        with patch("reconciliation.connect", return_value=conn), patch("reconciliation.fetch_changes", return_value=page):
            result = update_summaries()
        self.assertEqual(result["changed"], 1)
        self.assertFalse(result["has_more_data"])
        self.assertEqual(conn.execute.call_args.args[1], ("final", True, "4950"))
        self.assertEqual(conn.__exit__.call_args.args, (None, None, None))


if __name__ == "__main__":
    unittest.main()
