# Price levels in the weekly dashboard

The protected weekly report includes `price_level_source` and a `price_levels`
object per category/night. The dashboard displays the current snapshot level,
recommended grid level and calculated adult prices for all ten selling tariffs.
Existing report fields and tariff-comparison endpoints remain compatible.

## Sources and scope

- RACK/RACK2 were exported from TravelLine property 4950 on 2026-11-02 at
  14:44 Moscow time. The snapshot preserves 93 nights through 2027-02-02.
- All 34 level mappings and inheritance rules were read without modifications.
  BAR1–BAR6 deduct 400/800/1200/1600/2000/2400 RUB from RACK.
  BAR7–BAR10 deduct 2700/3000/3300/3600 RUB. Levels 13–34 deduct
  `(level-12)*150` RUB from RACK2. Level 1 is RACK; level 12 is RACK2.
- The category-specific calendar was manually read for 2026-11-02 through
  2026-11-08 inclusive and checked against the dynamic base tariff for all
  adult main placements. The full export does not extend calendar coverage.
- Selling-tariff meal supplements, markups and rounding use the separately
  verified rules already in `tariff_pricing.py`. These are calculated prices,
  not a confirmation that a tariff is currently bookable.

## Recommendation policy

The existing occupancy multiplier defines a target based on the current
one-adult base price. The nearest positive price among all 34 levels is selected;
ties prefer the current level, then the smaller price change. All adult main
placements and all selling tariffs use the same selected category/night level.
This is a transparent test rule, not a forecast or competitor-based optimizer.

Missing calendar, a current-base mismatch, stale/incomplete booking data,
past dates or sold-out inventory suppress proposals. The manual calendar
snapshot also expires when the report's Moscow date differs from its verification
date; refreshing bookings never refreshes price-level evidence. Snapshot levels
and prices remain labelled as historical source data. No inferred calendar is
created for unverified dates. Child and extra-place proposals are not generated.

## Refresh

Replace `price_levels_snapshot.json` only after a new read-only export and
category/date calendar verification. Update the verification date, observed adult
base prices and source hash together. Run the level tests and report tests.
No automatic TravelLine calendar API or background browser polling is installed.
No writes to TravelLine are implemented.
