"""Read TravelLine XLSX export into a lossless, deduplicated snapshot (stdlib only)."""
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
MONTHS={'янв':1,'февр':2,'мар':3,'апр':4,'мая':5,'июн':6,'июл':7,'авг':8,'сент':9,'окт':10,'нояб':11,'дек':12}
CATEGORIES=("Одноместный стандарт","Стандартный двухместный номер с одной большой или двумя раздельными кроватями","Улучшенный номер с большой двуспальной кроватью","Комфорт с большой двуспальной кроватью")


def extract(path):
    with ZipFile(path) as archive:
        strings=[]
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings=[''.join(x.itertext()) for x in ET.fromstring(archive.read('xl/sharedStrings.xml')).findall('s:si',NS)]
        sheets=[x for x in archive.namelist() if x.startswith('xl/worksheets/sheet') and x.endswith('.xml')]
        if len(sheets)!=1: raise ValueError('Expected one export sheet')
        rows=[]
        for row in ET.fromstring(archive.read(sheets[0])).findall('.//s:sheetData/s:row',NS):
            cells={}
            for cell in row.findall('s:c',NS):
                if cell.find('s:f',NS) is not None: raise ValueError('Formula cell requires inspection')
                value=cell.find('s:v',NS); inline=cell.find('s:is',NS)
                value=value.text if value is not None else ''.join(inline.itertext()) if inline is not None else ''
                if cell.get('t')=='s': value=strings[int(value)]
                col=''.join(x for x in cell.attrib['r'] if x.isalpha())
                cells[col]=value or None
            rows.append(cells)
    dates={};year=2026
    for col,value in rows[0].items():
        if col=='A' or not value:continue
        if value.isdigit() and len(value)==4:year=int(value);continue
        day,month=value.split()
        dates[col]=date(year,MONTHS[month],int(day)).isoformat()
    ordered=list(dates.values())
    if ordered!=[(date.fromisoformat(ordered[0])+timedelta(days=i)).isoformat() for i in range(len(ordered))]:
        raise ValueError('Non-contiguous export dates')
    plans=[];series=[];lookup={};plan=category=None
    for row in rows[1:]:
        label=row.get('A')
        if label and label.endswith(', RUB'):
            plan={'name':label[:-5],'currency':'RUB','categories':{}};plans.append(plan);category=None
        elif label in CATEGORIES:
            if plan is None:raise ValueError('Missing tariff')
            category={};plan['categories'][label]=category
        elif label:
            if category is None:raise ValueError('Unscoped row: '+label)
            if label in category:raise ValueError('Duplicate row')
            values=tuple(row.get(c) for c in dates)
            if values not in lookup:
                runs=[]
                for i,value in enumerate(values):
                    if not runs or runs[-1][1]!=value:runs.append([i+1,value])
                    else:runs[-1][0]=i+1
                lookup[values]=len(series);series.append(runs)
            category[label]=lookup[values]
    if len({p['name'] for p in plans})!=len(plans):raise ValueError('Duplicate tariff')
    if any(set(p['categories'])!=set(CATEGORIES) for p in plans):raise ValueError('Incomplete categories')
    return {'property_id':'4950','exported_at':'2026-10-31T18:58:00+03:00',
            'source_sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            'date_from':ordered[0],'date_to_exclusive':(date.fromisoformat(ordered[-1])+timedelta(days=1)).isoformat(),
            'days':len(ordered),'series':series,'tariffs':plans}


if __name__=='__main__':
    import sys
    data=extract(sys.argv[1])
    Path(sys.argv[2]).write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n')
    print(json.dumps({'tariffs':len(data['tariffs']),'days':data['days'],'series':len(data['series'])}))
