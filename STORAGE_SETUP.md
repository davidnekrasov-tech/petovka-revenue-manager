# PostgreSQL booking-summary import

Set `SYNC_API_KEY` to a long random secret in the NEW Timeweb application's environment. Keep the existing PG* and TravelLine variables. Do not commit any secrets. The old application has no PG* configuration and should not run this import.

After deployment, open `/docs`. Click **Authorize**, enter the key in the HTTP Bearer field, then:

1. POST `/api/storage/init` creates the two tables, idempotently.
2. POST `/api/storage/sync` imports one page of at most 100 booking summaries. Repeat until `completed` is true. Each request can make two TravelLine requests and take up to roughly 40 seconds. A timeout from the web proxy is not proof of failure: check status before retrying.
3. GET `/api/storage/status` shows stored count, committed page count and completion. No guest data or pagination tokens are returned.
4. POST `/api/storage/restart` starts a fresh full pass without deleting stored rows. Then repeat sync. There is no automatic schedule yet.

Import uses the existing property 4950 and existing `lastModification=2023-09-22T00:00:00Z` filter. Completion means all pages returned for this filter, not all historical hotel bookings. The stored payload is the TravelLine booking summary; detailed room stays, daily rates and occupancy are not imported in this stage. Cancelled summaries are retained and updated as returned by TravelLine. Records absent from a later pass are not deleted.

Tables: `tl_booking_summaries` (property + booking number primary key; JSONB summary and sync timestamp), `tl_sync_state` (committed continuation token and progress). Upserts and continuation checkpoint commit in a single transaction. An advisory transaction lock prevents concurrent imports. A failed page rolls back and can be retried. Schema creation is explicit/lazy; application startup does not require database availability.

All new storage routes require SYNC_API_KEY. Existing TravelLine routes retain their prior access behavior. This change does not add authentication to the whole service. Avoid pasting guest data or credentials in issues/logs.

Validation: `python -m pip install -r requirements.txt httpx`; `python -m unittest test_booking_storage -v`. Tests use mocked database connections to verify authorization, pagination validation, atomic checkpoint boundaries and completed-import behavior. A live PostgreSQL/TravelLine test is still required in Timeweb.
