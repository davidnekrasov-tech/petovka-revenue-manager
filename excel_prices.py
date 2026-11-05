"""Authenticated XLSX import into our database; no TravelLine write operations."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re
from zipfile import BadZipFile
from xml.etree.ElementTree import ParseError

import psycopg
from psycopg.types.json import Jsonb
from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from booking_storage import PROPERTY_ID, authorize, connect
from import_tariff_export import extract

router = APIRouter(prefix='/api/storage', tags=['Excel prices'], dependencies=[Depends(authorize)])
active_snapshot = ContextVar('tariff_snapshot', default=None)
MAX_BYTES = 2_000_000


@contextmanager
def use_snapshot(snapshot):
    token = active_snapshot.set(snapshot)
    try:
        yield
    finally:
        active_snapshot.reset(token)


def read_snapshot(connection, fallback):
    if connection.execute("SELECT to_regclass('public.tl_price_exports')").fetchone()[0] is None:
        return fallback
    row = connection.execute('SELECT payload FROM tl_price_exports WHERE property_id=%s', (PROPERTY_ID,)).fetchone()
    return row[0] if row else fallback


def validate_export(data, filename, exported_at, now, expected_names):
    if not re.fullmatch(r'ID_4950_[^/\\\\]+\.xlsx', filename, re.I):
        raise ValueError('Use the original ID_4950_....xlsx file from TravelLine')
    stamp = datetime.fromisoformat(exported_at)
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError('Export time must include a timezone')
    if stamp > now or stamp.year < 2020:
        raise ValueError('Invalid export time')
    snapshot = extract(data, stamp.isoformat())
    if {p['name'] for p in snapshot['tariffs']} != set(expected_names):
        raise ValueError('Export must contain all 10 selling tariffs; RACK/RACK2 alone is not supported')
    for plan in snapshot['tariffs']:
        for category, config in plan['categories'].items():
            required = {'Цена 1 осн.'} if category == 'Одноместный стандарт' else {'Цена 1 осн.', 'Цена 2 осн.'}
            if not required <= config.keys():
                raise ValueError('Export must include adult main placements')
            for label, series_id in config.items():
                if label.startswith('Цена'):
                    for _, raw in snapshot['series'][series_id]:
                        if raw is not None:
                            value = Decimal(raw)
                            if not value.is_finite() or value < 0 or value > 10_000_000:
                                raise ValueError('Invalid price')
    snapshot['uploaded_at'] = now.isoformat()
    snapshot['filename'] = filename
    snapshot['timestamp_basis'] = 'user_declared_export_time'
    snapshot['property_id_basis'] = 'original_filename_and_user_selected_property'
    return snapshot


def save_snapshot(snapshot):
    from tariff_pricing import SNAPSHOT
    try:
        with connect() as connection:
            connection.execute('SELECT pg_advisory_xact_lock(4950, 20)')
            connection.execute('''CREATE TABLE IF NOT EXISTS tl_price_exports (
                property_id text PRIMARY KEY, payload jsonb NOT NULL)''')
            current = read_snapshot(connection, SNAPSHOT)
            old_stamp = datetime.fromisoformat(current['exported_at'])
            new_stamp = datetime.fromisoformat(snapshot['exported_at'])
            if new_stamp < old_stamp or (new_stamp == old_stamp and snapshot['source_sha256'] != current['source_sha256']):
                raise HTTPException(409, 'A newer or different export is already stored')
            if snapshot['source_sha256'] == current['source_sha256']:
                return {'status': 'ok', 'unchanged': True, 'source': {k: current[k] for k in ('exported_at', 'date_from', 'date_to_exclusive', 'source_sha256')}}
            connection.execute('''INSERT INTO tl_price_exports(property_id,payload) VALUES (%s,%s)
                ON CONFLICT(property_id) DO UPDATE SET payload=excluded.payload''', (PROPERTY_ID, Jsonb(snapshot)))
        return {'status': 'ok', 'unchanged': False, 'tariff_count': len(snapshot['tariffs']),
                'days': snapshot['days'], 'source': {k: snapshot[k] for k in ('exported_at', 'date_from', 'date_to_exclusive', 'source_sha256')}}
    except psycopg.Error:
        raise HTTPException(503, 'Could not save prices to database') from None


@router.post('/tariffs/import')
async def import_prices(request: Request, filename: str, exported_at: str):
    """Upload original TL XLSX body; timestamp must include timezone. Atomic full replacement."""
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_BYTES:
            raise HTTPException(413, 'File exceeds 2 MB')
    from tariff_pricing import RULES
    try:
        snapshot = await run_in_threadpool(validate_export, bytes(body), filename, exported_at,
                                            datetime.now(timezone.utc), RULES)
    except (ValueError, KeyError, IndexError, TypeError, BadZipFile, ParseError, InvalidOperation, OverflowError):
        raise HTTPException(422, 'Invalid export: use original ID_4950 XLSX with all 10 tariffs, all categories and adult placements; check export time') from None
    return await run_in_threadpool(save_snapshot, snapshot)
