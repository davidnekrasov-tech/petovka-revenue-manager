import unittest
from datetime import date
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tariff_pricing import SNAPSHOT, exported_rows, compare_tariffs, router
from database_pricing import build_recommendations
from test_database_pricing import snapshot, NOW


def report(day='2026-11-02'):
    data=snapshot();data['dates'][0]['date']=day
    return build_recommendations(data,NOW,NOW)


class TariffTests(unittest.TestCase):
    def test_verified_rounding_accepts_november_first_breakfast(self):
        result=compare_tariffs(report('2026-11-01'),'Лучшая цена дня с завтраком!')
        placement=list(result['dates'][0]['tariffs'][0]['categories'].values())[3]['placements']['Цена 2 осн.']
        self.assertEqual(placement['suggested_price'],'8453.00')
        self.assertEqual(placement['withheld_reasons'],[])

    def test_ruble_rounding_is_upward_not_nearest(self):
        from tariff_pricing import round_tariff_price
        from decimal import Decimal
        self.assertEqual(round_tariff_price('Лучшая цена дня с завтраком!',Decimal('8452.01')),Decimal('8453'))
        self.assertEqual(round_tariff_price('Лучшая цена дня без завтрака!',Decimal('8452.01')),Decimal('8452.01'))

    def test_all_ten_tariffs_and_categories_retained(self):
        self.assertEqual(len(SNAPSHOT['tariffs']),10)
        self.assertTrue(all(len(p['categories'])==4 for p in SNAPSHOT['tariffs']))
        result=compare_tariffs(report())
        self.assertEqual(len(result['dates'][0]['tariffs']),10)
        self.assertFalse(result['automatically_updated'])

    def test_export_values_november_dates_and_zero_are_preserved(self):
        p=next(p for p in SNAPSHOT['tariffs'] if p['name']=='Лучшая цена дня без завтрака!')
        config=list(p['categories'].values())[3]
        self.assertEqual(exported_rows(config,'2026-11-01')['Цена 2 осн.'],'6562.50')
        self.assertEqual(exported_rows(config,'2026-11-02')['Цена 2 осн.'],'6405.00')
        self.assertIsNone(exported_rows(config,'2026-10-31'))
        # Check RLE preserves all 99 days, including blanks rather than filling them.
        self.assertTrue(all(runs[-1][0]==99 for runs in SNAPSHOT['series']))

    def test_no_occupancy_adjustment_keeps_exact_price(self):
        result=compare_tariffs(report(),'Лучшая цена дня без завтрака!')
        comfort=list(result['dates'][0]['tariffs'][0]['categories'].values())[3]
        self.assertEqual(comfort['placements']['Цена 2 осн.']['suggested_price'],'6405.00')

    def test_adjustment_is_based_on_each_tariff_and_placement(self):
        data=report()
        for c in data['dates'][0]['categories'].values():
            c.update(occupied=0,available=c['capacity'],withheld_reasons=[])
        data['dates'][0]['occupancy_percent']=0
        result=compare_tariffs(data,'Лучшая цена дня без завтрака!')
        comfort=list(result['dates'][0]['tariffs'][0]['categories'].values())[3]
        self.assertEqual(comfort['placements']['Цена 2 осн.']['suggested_price'],'5775.00')
        self.assertEqual(comfort['placements']['Цена 1 осн.']['suggested_price'],'5565.00')

    def test_meal_is_not_discounted_and_channel_ratios_survive(self):
        data=report()
        for c in data['dates'][0]['categories'].values():
            c.update(occupied=0,available=c['capacity'],withheld_reasons=[])
        data['dates'][0]['occupancy_percent']=0
        plans={p['name']:p for p in compare_tariffs(data)['dates'][0]['tariffs']}
        def price(name):
            return list(plans[name]['categories'].values())[3]['placements']['Цена 2 осн.']['suggested_price']
        self.assertEqual(price('Лучшая цена дня с завтраком!'),'7665.00')
        self.assertEqual(price('Тариф с завтраком для OTA'),'8614.00')
        self.assertEqual(price('Тариф без завтрака для ЯП'),'6875.00')

    def test_override_mismatch_withholds_instead_of_guessing(self):
        from tariff_pricing import linked_price
        from decimal import Decimal
        value,base,error=linked_price('Лучшая цена дня без завтрака!',list(SNAPSHOT['tariffs'][0]['categories'])[3],
                                      '2026-11-02','Цена 2 осн.',Decimal('9999'),.9)
        self.assertIsNone(value)
        self.assertEqual(error,'export_does_not_match_inheritance_rule')

    def test_missing_price_is_not_filled_from_adjacent_day(self):
        result=compare_tariffs(report('2027-02-07'))
        values=[v for p in result['dates'][0]['tariffs'] for c in p['categories'].values() for v in c['placements'].values()]
        self.assertTrue(all(v['exported_price'] is None and v['suggested_price'] is None for v in values))

    def test_closed_marker_prevents_suggestion_and_child_rows_retained(self):
        with patch('tariff_pricing.exported_rows',return_value={'Цена 1 осн.':'6000.00','Цена 2 осн.':'6200.00','Close/Open':'X','MinLOS':'3','Цена реб. (4-10 лет)':'500.00'}):
            result=compare_tariffs(report())
        category=list(result['dates'][0]['tariffs'][0]['categories'].values())[2]
        self.assertEqual(category['exported_rows']['MinLOS'],'3')
        self.assertEqual(category['exported_rows']['Цена реб. (4-10 лет)'],'500.00')
        self.assertIn('exported_close_marker',category['placements']['Цена 2 осн.']['withheld_reasons'])
        self.assertIsNone(category['placements']['Цена 2 осн.']['suggested_price'])

    def test_soldout_and_stale_data_stay_blocked(self):
        data=report()
        result=compare_tariffs(data)
        self.assertIsNone(list(result['dates'][0]['tariffs'][0]['categories'].values())[0]['placements']['Цена 1 осн.']['suggested_price'])
        for c in data['dates'][0]['categories'].values():c['withheld_reasons']=['summary_check_missing_or_stale']
        result=compare_tariffs(data)
        self.assertTrue(all(v['suggested_price'] is None for p in result['dates'][0]['tariffs'] for c in p['categories'].values() for v in c['placements'].values()))

    def test_auth_and_range_do_not_call_reader(self):
        app=FastAPI();app.include_router(router)
        with patch.dict('os.environ',{'SYNC_API_KEY':'test'}),TestClient(app) as client,patch('tariff_pricing.pricing_from_database') as read:
            self.assertEqual(client.get('/api/storage/tariffs').status_code,401)
            response=client.get('/api/storage/pricing/tariffs?date_from=2026-11-01&date_to=2026-11-01',headers={'Authorization':'Bearer test'})
            self.assertEqual(response.status_code,422)
            response=client.get('/api/storage/pricing/tariffs?date_from=2026-11-01&date_to=2026-11-02&tariff_name=missing',headers={'Authorization':'Bearer test'})
            self.assertEqual(response.status_code,404)
            read.assert_not_called()

if __name__=='__main__':unittest.main()
