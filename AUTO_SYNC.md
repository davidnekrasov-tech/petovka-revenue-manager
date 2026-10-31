# Automatic TravelLine synchronization

The application polls incremental booking summaries every 300 seconds, beginning
on startup after the initial import has finished. It stores only new/changed
summaries, then wakes the existing details worker. Details are fetched only when
their summary hash changed or their snapshot is missing. No rates or bookings are
written back to TravelLine. Repair blocks remain outside this calculation.

`tl_auto_sync` stores the shared enabled flag, schedule, last successful page,
retry count and sanitized error. A PostgreSQL session advisory lock prevents two
application instances from polling concurrently; the summary transaction lock
also serializes manual requests. The final TravelLine cursor is retained.
Backlogs advance one page per 5-second tick; idle polling happens every 5 minutes.
A crash can repeat a page safely because summary writes and cursor advancement
are committed atomically. The schedule survives application restarts.

HTTP 429 preserves Retry-After, with an exponential fallback starting at 120
seconds (up to 1800). Other handled synchronization errors also back off.
Unexpected failures log the exception class only and retry after 30 seconds.
Details keep their existing rate limiting, retries and separate status.
A manually paused or failed detail job is never automatically restarted; use
`POST /api/storage/details/start` after inspecting it. A running detail job may
finish while summary pagination continues; any newly stale snapshots are picked
up by the existing worker or the next poll.

Protected Swagger endpoints (use the existing SYNC_API_KEY value):

- `GET /api/storage/auto/status`: enabled, next run, last successful summary page,
  failures and last error. A successful summary poll does not prove details have
  completed: also check `/api/storage/details/status` and occupancy coverage.
- `POST /api/storage/auto/pause`: persistently pause polling. An in-flight page
  and an already running details import can finish. To pause both, also use
  `/api/storage/details/pause`.
- `POST /api/storage/auto/start`: enable polling and make the next tick due now.

Before manually restarting the initial summary import, pause automatic polling.
Automatic polling does not take over an unfinished manual initial import.
All existing manual sync/update/detail endpoints remain available.
No new environment variables or packages are required. Background work requires
the application process and database to remain available. There is no external
scheduler and no guarantee of an exact five-minute freshness during outages,
rate limits, a backlog or a paused/failed detail import.

Validation: mocked unit tests cover schedule/pause, incremental pagination,
initial-import protection, Retry-After, preservation of detail pause/retry, and
shutdown. Database session locking uses the same PostgreSQL mechanism as the
existing detail worker. Production scheduling and database migrations must be
confirmed through the protected status after deployment.
