"""Public UI shell; all hotel data is fetched through the protected report API."""
import base64
import hashlib
import re
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

@router.get('/dashboard', response_class=HTMLResponse, include_in_schema=False)
def dashboard():
    page = Path(__file__).with_name('dashboard.html').read_text()
    script = re.search(r'<script>(.*?)</script>', page, re.S).group(1)
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    return HTMLResponse(page, headers={
        'Cache-Control': 'no-store',
        'Referrer-Policy': 'no-referrer',
        'X-Content-Type-Options': 'nosniff',
        'Content-Security-Policy': "default-src 'none'; script-src 'sha256-" + digest + "'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
    })
