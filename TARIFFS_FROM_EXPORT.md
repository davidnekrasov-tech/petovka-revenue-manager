# All TravelLine tariffs from the export

The hotel authorized all ten tariffs from its 31 October 2026 18:58 Moscow export.
The snapshot contains dates 1 November 2026–7 February 2027 inclusive (99 dates).
Some later cells are blank: the covered calendar does not guarantee a populated
price. Blank values are retained and never forward-filled. No API tariff reading
or automatic price changes are introduced.

`tariff_snapshot.json` stores all tariff names, four category names, placement and
child price rows, Close/Open markers and MinLOS rows. Deduplicated value series
use run end indices (exclusive); this is lossless compression, not interpolation.
The snapshot includes SHA-256 of the original XLSX and its export timestamp.
`import_tariff_export.py` is the stdlib-only converter for this export layout.
It rejects formulas, multiple sheets, duplicate tariffs/row labels, missing room
categories and non-contiguous dates. Review a replacement before deployment.
The year separator column is not treated as a price date.

Protected endpoints using the existing SYNC_API_KEY:

- `GET /api/storage/tariffs`: source timestamp, date range and all ten tariff names.
- `GET /api/storage/pricing/tariffs?date_from=2026-11-01&date_to=2026-11-03`:
  all tariffs, per date and category; checkout exclusive, 1–31 nights.
  Optional `tariff_name` filters by exact exported name.

For each adult placement, return the exact exported price and a preliminary price
suggestion using the existing occupancy multiplier, followed by difference and
percentage change. Multipliers of one retain the original cents exactly; other
adjustments round to hundreds with decimal half-up rounding. The multiplier is
now exposed by calculate_category_price without altering its existing calculation.
Price suggestions remain withheld for sold-out categories, past nights, stale or
incomplete booking data, occupancy issues, dates outside the export, non-positive
or missing source prices and nonempty Close/Open markers. Original child rows and
restrictions are returned without calculating new child prices.

The tariffs share the same room inventory: never sum their availability as if
these were separate rooms. Blank Close/Open does not establish bookability.
MinLOS and other conditions still need review. Breakfast, commissions and
inherited tariff formulas are not separately modeled. Applying the occupancy
factor to a tariff's full exported adult price is a preliminary comparison only;
it is not an instruction to alter breakfast supplements or inherited tariff links.
No meal inclusion, channel eligibility or cancellation policy is inferred beyond
the exported tariff names. Read the full tariff settings before acting.

Booking occupancy continues to refresh every five minutes. The tariff snapshot
is static and does not refresh with bookings; responses explicitly say
`automatically_updated: false`. The original pricing endpoint remains available.
Live verification of the two new protected endpoints follows deployment.
