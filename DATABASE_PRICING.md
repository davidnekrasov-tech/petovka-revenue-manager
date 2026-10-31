# Price suggestions from database occupancy

Use protected `GET /api/storage/pricing?date_from=2026-10-31&date_to=2026-11-03`.
The checkout date is exclusive; a request can cover 1–90 nights. The existing
SYNC_API_KEY is required. This endpoint reads PostgreSQL only. It does not call
TravelLine or publish prices. Existing manual `/api/pricing` routes are unchanged.

Each date reports occupancy for all 15 rooms and for the four categories. Each
category reports its configured base price, suggested price per room/night, actual
rounded percentage change, reason, and any reasons for withholding a suggestion.
Reference prices remain 5000, 5500, 6500 and 7500 RUB from pricing.py. They are not
current TravelLine tariffs and need hotel approval before operational use.

The endpoint reuses the existing category occupancy rule: below 30% ×0.90;
30–60% ×1; 60–80% ×1.05; 80–100% ×1.15. Overall hotel occupancy at least 80%
sets a minimum multiplier of 1.15, and at least 90% sets 1.20. Existing rounding
to hundreds is retained. Sold-out categories return no suggested sale price.
This is a rule-based first version, not a trained forecast or competitor model.

All prices are withheld if imported snapshots are incomplete, the last successful
summary check is missing/older than 15 minutes, or occupancy reports quality
issues. Past nights (Moscow calendar) are withheld. Unknown categories and
inventory overflow also block suggestions. Booked nightly amounts are not used as
base prices; missing monetary amounts do not invalidate an otherwise valid room
count. No guest names, booking identifiers or secrets are returned.

Freshness uses tl_sync_state.updated_at, the successful poll time, rather than the
last changed booking timestamp (an idle poll is still fresh). It is captured before
loading the occupancy snapshot, so a later concurrent poll cannot make older data
look newly checked. Occupancy remains a consistent read of imported snapshots,
not a live TravelLine query. Coverage is included for inspection.

Repair blocks remain excluded by agreement; physical capacity stays 15.
Booking pace, lead time, holidays, competitor rates, channel commissions and
current tariff conditions are not model inputs. Review suggestions before use.

Validation: nine new tests cover observed 2/2/3/2 category counts, sold-out
categories, reference prices, incomplete/stale/invalid data, Moscow past dates,
missing monetary amounts, read-only routing and authentication. All 48 tests pass.
Live protected endpoint verification follows the Timeweb deployment.
