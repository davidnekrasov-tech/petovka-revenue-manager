# Refresh and reconcile imported bookings

The original import discarded the continuation cursor on the final page and `/sync` returned immediately after completion. This left later booking changes unprocessed. Final-page cursors are now preserved. This does not prove that stale data explains every difference from the TravelLine chessboard.

Use the existing SYNC_API_KEY in `/docs`; no new credentials are required.

1. POST `/api/storage/updates` fetches one page of changes. Repeat until `has_more_data` is false. `changed` counts new/different summary payloads, not room-nights. On HTTP 429, wait before retrying; this manual endpoint does not automatically retry. Failures roll back the page and its cursor atomically.
2. Existing deployments without a final cursor fall back to the last summary sync state timestamp minus two days. Newer deployments use the retained final cursor, including idle polls that return the same cursor. Unchanged overlap payloads are not rewritten. This fallback is for post-import refresh, not a replacement for the initial historical import.
3. POST `/api/storage/details/start` refreshes details of new/changed summaries. Wait for `/details/status` to report no pending entries/errors. Unchanged snapshots are not re-fetched.
4. GET `/api/storage/occupancy` recalculates counts from current imported snapshots.
5. GET `/api/storage/occupancy/audit?date_from=2026-10-30&date_to=2026-11-02` lists overlapping room stays with booking number, category, dates, statuses, detail timestamp and inclusion/exclusion reason. It includes stale/cancelled overlapping stored details for investigation. It excludes guest names/contacts and does not reveal tokens. Date range is 1–31 nights with exclusive checkout date.

Compare audit booking numbers against TravelLine cards, including unassigned-room reservations. The audit cannot list a booking that was never imported, and timestamps may differ from a later chessboard screenshot. It does not infer guest identities or silently replace the aggregate figures with screenshot counts. Read Reservation API supports Booking Engine, Channel Manager and WebPMS per TravelLine's developer documentation; missing desk bookings should not be presumed unsupported without evidence.

No recurring summary polling is configured by this patch. Run `python -m unittest test_reconciliation test_occupancy test_booking_storage test_booking_details -q`. Tests use mocked network/database boundaries; actual refreshed counts require Timeweb verification.
