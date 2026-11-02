import unittest
from datetime import datetime, timezone
from decimal import Decimal
from price_levels import GRID, base_rows, recommend_level

NOW = datetime(2026, 11, 2, 13, tzinfo=timezone.utc)
SINGLE = 'Одноместный стандарт'
COMFORT = 'Комфорт с большой двуспальной кроватью'


class LevelTests(unittest.TestCase):
    def inventory(self, occupied=0, reasons=None):
        return {'occupied': occupied, 'withheld_reasons': reasons or []}

    def test_all_28_observed_category_dates_match_both_adult_placements(self):
        for night, categories in GRID['observed_base_prices'].items():
            for category, observed in categories.items():
                self.assertEqual(base_rows(night, category, GRID['calendar'][night][category]),
                                 {k: Decimal(v) for k, v in observed.items()})

    def test_one_shared_level_and_tariff_markup_meals_rounding(self):
        r = recommend_level('2026-11-02', COMFORT, self.inventory(), 0, NOW)
        self.assertEqual(r['current_level'], 33)
        self.assertIn(r['recommended_level'], range(1, 35))
        self.assertEqual(r['recommended_level'], 34)
        self.assertEqual(r['recommended_base_prices']['Цена 2 осн.'], '5800.00')
        plans = {p['name']: p['placements'] for p in r['tariffs']}
        self.assertEqual(len(plans), 10)
        self.assertEqual(plans['Тариф с надбавкой для ОТА']['Цена 1 осн.']['current_price'], '6785.00')
        self.assertEqual(plans['Тариф с завтраком для OTA']['Цена 2 осн.']['suggested_price'], '8968.00')
        self.assertEqual(plans['Лучшая цена дня с завтраком!']['Цена 1 осн.']['suggested_price'], '6825.00')

    def test_no_free_form_prices_and_neutral_factor_keeps_current_level(self):
        r = recommend_level('2026-11-05', SINGLE, self.inventory(1), 40, NOW)
        self.assertEqual(r['recommended_level'], r['current_level'])
        self.assertEqual(r['current_base_prices'], r['recommended_base_prices'])

    def test_missing_stale_future_verification_and_inventory_errors_withhold(self):
        for night, now, inventory, reason in [
            ('2026-11-09', NOW, self.inventory(), 'level_calendar_missing'),
            ('2026-11-02', NOW.replace(day=3), self.inventory(), 'level_calendar_stale'),
            ('2026-11-02', NOW.replace(day=1), self.inventory(), 'level_calendar_stale'),
            ('2026-11-02', NOW, self.inventory(2, ['sold_out']), 'sold_out'),
            ('2026-11-02', NOW, self.inventory(0, ['summary_check_missing_or_stale']), 'summary_check_missing_or_stale')]:
            r = recommend_level(night, SINGLE, inventory, 0, now)
            self.assertIn(reason, r['withheld_reasons'])
            self.assertIsNone(r['recommended_level'])
            self.assertTrue(all(v['suggested_price'] is None for p in r['tariffs'] for v in p['placements'].values()))

    def test_mismatch_withholds_and_outside_grid_is_missing(self):
        from unittest.mock import patch
        with patch.dict(GRID['calendar']['2026-11-02'], {SINGLE: 31}):
            r = recommend_level('2026-11-02', SINGLE, self.inventory(), 0, NOW)
            self.assertIn('level_price_not_verified', r['withheld_reasons'])
            self.assertIsNone(r['recommended_level'])
        self.assertEqual(base_rows('2027-02-03', SINGLE, 34), {})

if __name__ == '__main__':
    unittest.main()
