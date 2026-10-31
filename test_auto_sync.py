import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
import auto_sync


class AutoSyncTests(unittest.TestCase):
    def connection(self, enabled=True, due=None, failures=0, initial=(True, 88)):
        now = datetime(2026, 10, 31, tzinfo=timezone.utc)
        conn = MagicMock()
        conn.execute.return_value.fetchone.side_effect = [(enabled, due or now, failures, False), initial]
        return conn, now

    def test_paused_and_not_due_do_not_call_travelline(self):
        for enabled, future in [(False, False), (True, True)]:
            conn, now = self.connection(enabled=enabled)
            if future:
                conn.execute.return_value.fetchone.side_effect = [(True, now + timedelta(seconds=10), 0, False)]
            with patch('auto_sync.update_summaries') as fetch:
                auto_sync.poll_once(conn, now)
            fetch.assert_not_called()

    def test_empty_initial_import_is_not_started_automatically(self):
        conn, now = self.connection(initial=(False, 0))
        with patch('auto_sync.update_summaries') as fetch:
            auto_sync.poll_once(conn, now)
        fetch.assert_not_called()
        self.assertIn('INITIAL_IMPORT_REQUIRED', conn.execute.call_args.args[0])

    def test_partial_manual_import_is_not_taken_over(self):
        conn, now = self.connection(initial=(False, 10))
        with patch('auto_sync.update_summaries') as fetch:
            auto_sync.poll_once(conn, now)
        fetch.assert_not_called()

    def test_final_page_wakes_details_and_schedules_five_minutes(self):
        conn, now = self.connection()
        with patch('auto_sync.update_summaries', return_value={'has_more_data':False}), patch('auto_sync.wake_details') as wake:
            auto_sync.poll_once(conn, now)
        wake.assert_called_once_with(conn)
        self.assertEqual(conn.execute.call_args.args[1][0], now + timedelta(seconds=300))

    def test_backlog_is_drained_without_starting_details_early(self):
        conn, now = self.connection()
        with patch('auto_sync.update_summaries', return_value={'has_more_data':True}), patch('auto_sync.wake_details') as wake:
            auto_sync.poll_once(conn, now)
        wake.assert_not_called()
        self.assertEqual(conn.execute.call_args.args[1][0], now + timedelta(seconds=5))

    def test_rate_limit_keeps_retry_after_and_redacts_message(self):
        conn, now = self.connection()
        error = HTTPException(502, 'TravelLine returned HTTP 429', headers={'Retry-After':'900'})
        with patch('auto_sync.update_summaries', side_effect=error), patch('auto_sync.wake_details') as wake:
            auto_sync.poll_once(conn, now)
        wake.assert_not_called()
        params = conn.execute.call_args.args[1]
        self.assertEqual(params[:3], (now + timedelta(seconds=900), 'TRAVELLINE_HTTP_429', 1))

    def test_details_pause_failure_and_retry_are_preserved(self):
        conn = MagicMock()
        with patch('auto_sync.prepare_details'), patch('auto_sync.launch_details'):
            auto_sync.wake_details(conn)
        sql = conn.execute.call_args.args[0]
        self.assertIn("state = 'completed'", sql)
        self.assertNotIn('retry_at =', sql)
        self.assertNotIn('last_error =', sql)

    def test_shutdown_prevents_worker_queries(self):
        auto_sync._stop.set()
        try:
            with patch('auto_sync.connect') as connect:
                auto_sync.worker()
            connect.assert_not_called()
        finally:
            auto_sync._stop.clear()


if __name__ == '__main__':
    unittest.main()
