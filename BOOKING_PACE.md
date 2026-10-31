# Booking creation cohorts

Protected GET `/api/storage/pace?date_from=2026-11-01&date_to=2026-11-08`.
Dates are stay nights, checkout exclusive, limited to 90 nights. Rolling windows
are the preceding 24, 72, and 168 hours, lower exclusive and upper inclusive.

The metric counts currently Active bookings (summary AND current detail status)
created within each window and overlapping the stay range. It separately counts
room nights and per-night/category room stays. These are creation cohorts of the
current imported snapshot, NOT net historical pickup. A later cancellation or
stay change changes the cohort. Creation times without offsets are interpreted
in Europe/Moscow. Future or missing creation times are excluded and reported.
The booking count is null if creation coverage is incomplete; known counts remain
available explicitly. Cancellation counts and net pickup remain null because the
system has no cancellation-event history. Never substitute lastModifiedDateTime
for cancellation time.

Queries use a consistent read-only repeatable-read DB transaction. Stale detail
hashes are excluded. Coverage and latest summary-check freshness are included;
status is partial for incomplete or stale imports or invalid creation/stay dates.
The endpoint creates no tables and performs no TravelLine calls or writes.
65 tests passed, covering cohorts, boundary times, hotel timezone, room-stay
counting, cancellation exclusion, missing timestamps, auth and range validation.
