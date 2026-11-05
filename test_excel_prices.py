import copy
import io
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock
from zipfile import ZipFile
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi import HTTPException
from excel_prices import router, validate_export, save_snapshot, use_snapshot, read_snapshot
from tariff_pricing import RULES, SNAPSHOT, exported_rows, compare_tariffs
from test_tariff_pricing import report

NOW = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)


def workbook(year=2026, incomplete=False, formula=False):
    # Minimal genuine XLSX XML shape, all 10 plans and adult placements.
    from xml.sax.saxutils import escape
    rows = [[str(year), '5 нояб', '6 нояб']]
    for plan in list(RULES)[:1 if incomplete else 10]:
        rows.append([plan+', RUB'])
        for category in SNAPSHOT['tariffs'][0]['categories']:
            rows.append([category])
            rows.append(['Цена 1 осн.', '6000.00', '6100.00'])
            if category != 'Одноместный стандарт':
                rows.append(['Цена 2 осн.', '6200.00', '6300.00'])
    xml='<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
    for i, values in enumerate(rows,1):
        xml+='<row>'
        for j, v in enumerate(values):
            xml+=f'<c r="{chr(65+j)}{i}" t="inlineStr"><is><t>{escape(v)}</t></is>' + ('<f>1+1</f>' if formula and i==4 and j==1 else '') + '</c>'
        xml+='</row>'
    xml+='</sheetData></worksheet>'
    data=io.BytesIO()
    with ZipFile(data,'w') as z:z.writestr('xl/worksheets/sheet1.xml',xml)
    return data.getvalue()


class ExcelTests(unittest.TestCase):
    def validate(self,data=None,stamp='2026-11-05T14:00:00+03:00',filename='ID_4950_prices.xlsx'):
        return validate_export(data or workbook(),filename,stamp,NOW,RULES)

    def test_complete_import_and_next_year_header(self):
        data=self.validate(workbook(2027))
        self.assertEqual(data['date_from'],'2027-11-05')
        self.assertEqual(len(data['tariffs']),10)
        self.assertEqual(data['exported_at'],'2026-11-05T14:00:00+03:00')

    def test_partial_wrong_property_formula_and_future_rejected(self):
        for kwargs in ({'data':workbook(incomplete=True)}, {'filename':'ID_999_prices.xlsx'},
                       {'data':workbook(formula=True)}, {'stamp':'2026-11-06T12:00:00+03:00'},
                       {'stamp':'2026-11-05T12:00:00'}):
            with self.subTest(kwargs=list(kwargs)),self.assertRaises(ValueError): self.validate(**kwargs)

    def test_request_snapshot_isolated_and_restored(self):
        modified=copy.deepcopy(SNAPSHOT);modified['series']=[[[modified['days'],'123.00']] for _ in modified['series']]
        config=list(SNAPSHOT['tariffs'][0]['categories'].values())[0]
        with use_snapshot(modified):self.assertEqual(exported_rows(config,'2026-11-02')['Цена 1 осн.'],'123.00')
        self.assertNotEqual(exported_rows(config,'2026-11-02')['Цена 1 осн.'],'123.00')

    def test_stale_export_keeps_prices_but_withholds_suggestions(self):
        data=report();data['freshness']['generated_at']=NOW
        r=compare_tariffs(data)
        values=[v for p in r['dates'][0]['tariffs'] for c in p['categories'].values() for v in c['placements'].values()]
        self.assertTrue(any(v['exported_price'] is not None for v in values))
        self.assertTrue(all(v['suggested_price'] is None and 'tariff_export_stale' in v['withheld_reasons'] for v in values))

    def test_auth_validation_and_size_before_save(self):
        app=FastAPI();app.include_router(router)
        with patch.dict('os.environ',{'SYNC_API_KEY':'test'}),TestClient(app) as c,patch('excel_prices.save_snapshot') as save:
            url='/api/storage/tariffs/import?filename=ID_4950_prices.xlsx&exported_at=2026-11-02T09:26:00%2B03:00'
            self.assertEqual(c.post(url,content=workbook()).status_code,401)
            h={'Authorization':'Bearer test'}
            self.assertEqual(c.post(url,content=b'bad',headers=h).status_code,422)
            self.assertEqual(c.post(url,content=b'x'*2_000_001,headers=h).status_code,413)
            save.assert_not_called()
            save.return_value={'status':'ok'}
            self.assertEqual(c.post(url,content=workbook(),headers=h).status_code,200)
            self.assertEqual(save.call_args.args[0]['days'],2)

    def test_persist_and_reject_older_without_replacing(self):
        conn=MagicMock();cm=MagicMock();cm.__enter__.return_value=conn
        with patch('excel_prices.connect',return_value=cm),patch('excel_prices.read_snapshot',return_value=SNAPSHOT):
            self.assertFalse(save_snapshot(self.validate())['unchanged'])
            self.assertTrue(any('INSERT INTO tl_price_exports' in str(call) for call in conn.execute.call_args_list))
        conn.reset_mock()
        newer=self.validate()
        with patch('excel_prices.connect',return_value=cm),patch('excel_prices.read_snapshot',return_value=newer):
            with self.assertRaises(HTTPException) as error:save_snapshot(SNAPSHOT)
            self.assertEqual(error.exception.status_code,409)
            self.assertFalse(any('INSERT INTO tl_price_exports' in str(call) for call in conn.execute.call_args_list))

    def test_duplicate_does_not_retimestamp_old_prices(self):
        same=copy.deepcopy(SNAPSHOT);same['exported_at']=NOW.isoformat()
        cm=MagicMock()
        with patch('excel_prices.connect',return_value=cm),patch('excel_prices.read_snapshot',return_value=SNAPSHOT):
            r=save_snapshot(same)
        self.assertTrue(r['unchanged'])
        self.assertEqual(r['source']['exported_at'],SNAPSHOT['exported_at'])

    def test_report_uses_uploaded_snapshot_instead_of_bundled_prices(self):
        from weekly_report import build_report
        from test_weekly_report import records, START, END, COVERAGE, NOW as REPORT_NOW, CATEGORY
        uploaded=copy.deepcopy(SNAPSHOT)
        uploaded['exported_at']=REPORT_NOW.isoformat()
        uploaded['series']=[[[uploaded['days'],'123.00']] for _ in uploaded['series']]
        result=build_report(records(),START,END,COVERAGE,REPORT_NOW,REPORT_NOW,uploaded)
        self.assertEqual(result['tariff_source']['exported_at'],REPORT_NOW.isoformat())
        first=result['dates'][0]['categories'][CATEGORY]['tariffs'][0]
        self.assertEqual(first['placements']['Цена 1 осн.']['exported_price'],'123.00')
        self.assertNotEqual(SNAPSHOT['series'],uploaded['series'])

    def test_database_restart_reads_saved_payload(self):
        conn=MagicMock();conn.execute.return_value.fetchone.side_effect=[('tl_price_exports',),(self.validate(),)]
        self.assertEqual(read_snapshot(conn,SNAPSHOT)['date_from'],'2026-11-05')


if __name__=='__main__':unittest.main()
