import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from booking_storage import make_router, validate_page


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"SYNC_API_KEY": "test-secret"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.fetch = MagicMock()
        app = FastAPI()
        app.include_router(make_router(self.fetch))
        self.client = TestClient(app)
        self.headers = {"Authorization": "Bearer test-secret"}

    def database(self):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        return connection

    def test_unauthorized_never_touches_database(self):
        with patch("booking_storage.connect") as connect:
            for path in ("init", "sync", "restart"):
                self.assertEqual(self.client.post("/api/storage/" + path).status_code, 401)
            self.assertEqual(self.client.get("/api/storage/status").status_code, 401)
            connect.assert_not_called()

    def test_unconfigured_key_fails_closed(self):
        with patch.dict(os.environ, {"SYNC_API_KEY": ""}):
            self.assertEqual(self.client.post("/api/storage/sync", headers=self.headers).status_code, 503)

    def test_pagination_rejects_missing_or_repeated_cursor(self):
        for token in (None, "old"):
            with self.assertRaises(HTTPException):
                validate_page({"status": "ok", "bookings": [], "has_more_data": True, "continue_token": token}, "old")

    def test_page_upsert_and_checkpoint_share_transaction(self):
        connection = self.database()
        connection.execute.return_value.fetchone.side_effect = [(True,), ("old", False, 2)]
        self.fetch.return_value = {"status": "ok", "bookings": [{"number": "B1", "status": "Cancelled"}], "has_more_data": True, "continue_token": "next"}
        with patch("booking_storage.connect", return_value=connection):
            response = self.client.post("/api/storage/sync", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "saved": 1, "completed": False, "pages": 3})
        self.fetch.assert_called_once_with("old")
        calls = connection.execute.call_args_list
        self.assertTrue(any("ON CONFLICT (property_id, booking_number)" in call.args[0] for call in calls))
        checkpoint = [call for call in calls if "pages = pages + 1" in call.args[0]][0]
        self.assertEqual(checkpoint.args[1], ("next", False, "4950"))
        self.assertEqual(connection.__exit__.call_args.args, (None, None, None))

    def test_completed_import_does_not_refetch(self):
        connection = self.database()
        connection.execute.return_value.fetchone.side_effect = [(True,), (None, True, 4)]
        with patch("booking_storage.connect", return_value=connection):
            response = self.client.post("/api/storage/sync", headers=self.headers)
        self.assertTrue(response.json()["completed"])
        self.fetch.assert_not_called()

    def test_malformed_page_rolls_back_without_advancing_cursor(self):
        connection = self.database()
        connection.execute.return_value.fetchone.side_effect = [(True,), (None, False, 0)]
        connection.__exit__.return_value = False
        self.fetch.return_value = {"status": "ok", "bookings": [{}], "has_more_data": False}
        with patch("booking_storage.connect", return_value=connection):
            response = self.client.post("/api/storage/sync", headers=self.headers)
        self.assertEqual(response.status_code, 502)
        self.assertFalse(any("UPDATE tl_sync_state" in call.args[0] for call in connection.execute.call_args_list))
        self.assertIsNotNone(connection.__exit__.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
