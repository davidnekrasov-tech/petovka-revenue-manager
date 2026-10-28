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

## Background detail import

The existing `SYNC_API_KEY` protects all `/api/storage/details/*` routes. No new environment variable is needed.

1. Wait for the new deployment, open `/docs` and authorize with the existing key.
2. POST `/api/storage/details/start` once. It requires the summary import to be completed and responds immediately with HTTP 202. The background worker fetches details for all saved summaries, including cancelled bookings. Closing the browser does not stop it.
3. GET `/api/storage/details/status` reports `total`, `saved`, `pending`, `errors`, `state`, `retry_at` and safe error codes. `completed: true` means all current summaries have details and no recorded errors. If `state` is `completed` but `errors` is nonzero, the pass ended with errors; do not treat it as a complete dataset.
4. POST `/api/storage/details/pause` stops before the next booking (an in-flight request may still finish). POST start again resumes pending work, without refetching unchanged saved summaries or clearing a Retry-After cooldown. No data is deleted.

The worker uses one sequential detail request followed by a one-second pause, caches OAuth tokens and renews them before expiry. HTTP 429 honors Retry-After (seconds or HTTP-date), with exponential fallback; network/5xx errors back off too. Eight consecutive retryable failures stop the job with `state: failed`; start resumes it after investigation. 404s are recorded per booking and counted as errors rather than silently treated as successful details. Invalid response structure or permissions errors stop the import. Guest contact/name fields are excluded from detail storage; room dates/types, aggregate counts, daily rates and totals are retained. No booking payload is exposed by the new status routes.

Successful details are committed per booking. PostgreSQL advisory session locking prevents two workers from making requests simultaneously. Summary hashes determine whether a snapshot is current; changed summaries are fetched on the next started pass. A running job resumes after an application restart while `state = running`; paused/completed jobs do not automatically start a new pass. The worker polls its persistent state every five seconds and retries database failures every 30 seconds. This is an in-app worker, not an independent queue: the application must remain running. New summary polling is not scheduled by this change.

This stage does not change existing occupancy/revenue calculations. Financial values remain in their source fields (`priceBeforeTax`, `priceAfterTax`, etc.); they are not presented as collected payments or realized revenue.

Run `python -m unittest test_booking_storage test_booking_details -v` for authorization, field filtering, retry delays, token reuse, pagination and per-booking commit tests. These tests mock network/database boundaries. Live database/TravelLine verification remains required after deployment.
