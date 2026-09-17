from fastapi import FastAPI
from datetime import datetime
from data import revenue_data
from analytics import calculate_analytics
from forecast import calculate_forecast
from recommendations import generate_recommendations
from ai_assistant import generate_ai_report
from hotel_profile import hotel

app = FastAPI(
    title="Petrovka Revenue Manager",
    version="0.1.0"
)


@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "Petrovka Revenue Manager",
        "version": "0.1.0"
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow()
    }
@app.get("/api/travelline/test")
def travelline_test():
    import json
    import os
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen

    client_id = os.getenv("TRAVELLINE_CLIENT_ID")
    client_secret = os.getenv("TRAVELLINE_CLIENT_SECRET")

    if not client_id or not client_secret:
        return {
            "status": "error",
            "message": "TravelLine credentials are missing"
        }

    data = urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode("utf-8")

    request = Request(
        "https://partner.tlintegration.com/auth/token",
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded"
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(
                response.read().decode("utf-8")
            )

        return {
            "status": "ok",
            "token_received": bool(
                payload.get("access_token")
            ),
            "expires_in": payload.get("expires_in"),
        }

    except Exception as e:
        return {
            "status": "error",
            "error_type": type(e).__name__,
            "message": str(e)
        }



@app.get("/api/revenue")
def revenue():
    return calculate_analytics()
    total_revenue = sum(item.revenue for item in revenue_data)
    total_orders = sum(item.orders for item in revenue_data)

    average_check = 0
    if total_orders:
        average_check = total_revenue / total_orders

    return {
        "currency": "RUB",
        "total_revenue": total_revenue,
        "total_orders": total_orders,
        "average_check": round(average_check, 2),
        "days": revenue_data
    }


@app.get("/api/forecast")
def forecast():
    return calculate_forecast()


@app.get("/api/recommendations")
def recommendations():
    return generate_recommendations()


@app.get("/api/assistant")
def assistant():
    return generate_ai_report()
import os
@app.get("/api/travelline/properties")
def travelline_properties():
    import json
    import os
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen

    client_id = os.getenv("TRAVELLINE_CLIENT_ID")
    client_secret = os.getenv("TRAVELLINE_CLIENT_SECRET")

    data = urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode("utf-8")

    token_request = Request(
        "https://partner.tlintegration.com/auth/token",
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded"
        },
        method="POST",
    )

    with urlopen(token_request, timeout=20) as response:
        token_data = json.loads(
            response.read().decode("utf-8")
        )

    access_token = token_data["access_token"]

    request = Request(
        "https://partner.tlintegration.com/api/content/v1/properties",
        headers={
            "Authorization": f"Bearer {access_token}"
        },
        method="GET",
    )

    with urlopen(request, timeout=20) as response:
        properties = json.loads(
            response.read().decode("utf-8")
        )

    return properties
@app.get("/api/travelline/bookings")
def travelline_bookings():
    import json
    import os
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen

    client_id = os.getenv("TRAVELLINE_CLIENT_ID")
    client_secret = os.getenv("TRAVELLINE_CLIENT_SECRET")

    data = urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode("utf-8")

    token_request = Request(
        "https://partner.tlintegration.com/auth/token",
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded"
        },
        method="POST",
    )

    with urlopen(token_request, timeout=20) as response:
        token_data = json.loads(
            response.read().decode("utf-8")
        )

    access_token = token_data["access_token"]

    request = Request(
        "https://partner.tlintegration.com/api/read-reservation/v1/properties/4950/bookings?count=100",
        headers={
            "Authorization": f"Bearer {access_token}"
        },
        method="GET",
    )

    with urlopen(request, timeout=20) as response:
        bookings = json.loads(
            response.read().decode("utf-8")
        )

    return bookings
@app.get("/api/travelline/booking-structure")
def travelline_booking_structure():
    import json
    import os
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen

    client_id = os.getenv("TRAVELLINE_CLIENT_ID")
    client_secret = os.getenv("TRAVELLINE_CLIENT_SECRET")

    data = urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode("utf-8")

    token_request = Request(
        "https://partner.tlintegration.com/auth/token",
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded"
        },
        method="POST",
    )

    with urlopen(token_request, timeout=20) as response:
        token_data = json.loads(
            response.read().decode("utf-8")
        )

    access_token = token_data["access_token"]

    request = Request(
        "https://partner.tlintegration.com/api/read-reservation/v1/properties/4950/bookings?count=100",
        headers={
            "Authorization": f"Bearer {access_token}"
        },
        method="GET",
    )

    with urlopen(request, timeout=20) as response:
        bookings = json.loads(
            response.read().decode("utf-8")
        )

    if isinstance(bookings, dict):
        top_level_keys = list(bookings.keys())
    else:
        top_level_keys = []

    return {
        "type": type(bookings).__name__,
        "top_level_keys": top_level_keys
    }
@app.get("/api/travelline/booking-fields")
def travelline_booking_fields():
    import json
    import os
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen

    client_id = os.getenv("TRAVELLINE_CLIENT_ID")
    client_secret = os.getenv("TRAVELLINE_CLIENT_SECRET")

    data = urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode("utf-8")

    token_request = Request(
        "https://partner.tlintegration.com/auth/token",
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded"
        },
        method="POST",
    )

    with urlopen(token_request, timeout=20) as response:
        token_data = json.loads(
            response.read().decode("utf-8")
        )

    access_token = token_data["access_token"]

    request = Request(
        "https://partner.tlintegration.com/api/read-reservation/v1/properties/4950/bookings?count=100",
        headers={
            "Authorization": f"Bearer {access_token}"
        },
        method="GET",
    )

    with urlopen(request, timeout=20) as response:
        bookings = json.loads(
            response.read().decode("utf-8")
        )

    summaries = bookings.get("bookingSummaries", [])

    first_booking = summaries[0] if summaries else {}

    return {
        "booking_count": len(summaries),
        "first_booking_keys": list(first_booking.keys())
    }
@app.get("/api/travelline/booking-details")
def travelline_booking_details():
    import json
    import os
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen

    client_id = os.getenv("TRAVELLINE_CLIENT_ID")
    client_secret = os.getenv("TRAVELLINE_CLIENT_SECRET")

    data = urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode("utf-8")

    token_request = Request(
        "https://partner.tlintegration.com/auth/token",
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded"
        },
        method="POST",
    )

    with urlopen(token_request, timeout=20) as response:
        token_data = json.loads(
            response.read().decode("utf-8")
        )

    access_token = token_data["access_token"]

    request = Request(
        "https://partner.tlintegration.com/api/read-reservation/v1/properties/4950/bookings?count=1",
        headers={
            "Authorization": f"Bearer {access_token}"
        },
        method="GET",
    )

    with urlopen(request, timeout=20) as response:
        bookings = json.loads(
            response.read().decode("utf-8")
        )

    summaries = bookings.get("bookingSummaries", [])

    if not summaries:
        return {"booking_found": False}

    first_booking = summaries[0]

    return {
        "booking_found": True,
        "master_type": type(first_booking.get("master")).__name__,
        "master_keys": list(first_booking.get("master", {}).keys())
            if isinstance(first_booking.get("master"), dict) else [],
        "procuration_type": type(first_booking.get("procuration")).__name__,
        "procuration_keys": list(first_booking.get("procuration", {}).keys())
            if isinstance(first_booking.get("procuration"), dict) else []
    }
@app.get("/api/travelline/booking-fields")
def travelline_booking_fields():
    import json
    import os
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen

    client_id = os.getenv("TRAVELLINE_CLIENT_ID")
    client_secret = os.getenv("TRAVELLINE_CLIENT_SECRET")

    data = urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode("utf-8")

    token_request = Request(
        "https://partner.tlintegration.com/auth/token",
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded"
        },
        method="POST",
    )

    with urlopen(token_request, timeout=20) as response:
        token_data = json.loads(
            response.read().decode("utf-8")
        )

    access_token = token_data["access_token"]

    request = Request(
        "https://partner.tlintegration.com/api/read-reservation/v1/properties/4950/bookings?count=1",
        headers={
            "Authorization": f"Bearer {access_token}"
        },
        method="GET",
    )

    with urlopen(request, timeout=20) as response:
        bookings = json.loads(
            response.read().decode("utf-8")
        )

    summaries = bookings.get("bookingSummaries", [])

    if not summaries:
        return {
            "booking_found": False
        }

    booking = summaries[0]
    fields = {}

    for key, value in booking.items():
        if isinstance(value, dict):
            fields[key] = {
                "type": "dict",
                "keys": list(value.keys())
            }
        elif isinstance(value, list):
            fields[key] = {
                "type": "list",
                "length": len(value)
            }
        else:
            fields[key] = {
                "type": type(value).__name__
            }

    return {
        "booking_found": True,
        "fields": fields
    }
@app.get("/api/travelline/summary")
def travelline_summary():
    import json
    import os
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen

    client_id = os.getenv("TRAVELLINE_CLIENT_ID")
    client_secret = os.getenv("TRAVELLINE_CLIENT_SECRET")

    data = urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode("utf-8")

    token_request = Request(
        "https://partner.tlintegration.com/auth/token",
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded"
        },
        method="POST",
    )

    with urlopen(token_request, timeout=20) as response:
        token_data = json.loads(
            response.read().decode("utf-8")
        )

    access_token = token_data["access_token"]

    request = Request(
        "https://partner.tlintegration.com/api/read-reservation/v1/properties/4950/bookings?count=100",
        headers={
            "Authorization": f"Bearer {access_token}"
        },
        method="GET",
    )

    with urlopen(request, timeout=20) as response:
        bookings = json.loads(
            response.read().decode("utf-8")
        )

    summaries = bookings.get("bookingSummaries", [])

    return {
        "booking_count": len(summaries),
        "bookings": summaries
    }
@app.get("/api/travelline/booking-structure")
def travelline_booking_structure():
    import json
    import os
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen

    client_id = os.getenv("TRAVELLINE_CLIENT_ID")
    client_secret = os.getenv("TRAVELLINE_CLIENT_SECRET")

    data = urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode("utf-8")

    token_request = Request(
        "https://partner.tlintegration.com/auth/token",
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded"
        },
        method="POST",
    )

    with urlopen(token_request, timeout=20) as response:
        token_data = json.loads(
            response.read().decode("utf-8")
        )

    access_token = token_data["access_token"]

    request = Request(
        "https://partner.tlintegration.com/api/read-reservation/v1/properties/4950/bookings?count=100",
        headers={
            "Authorization": f"Bearer {access_token}"
        },
        method="GET",
    )

    with urlopen(request, timeout=20) as response:
        bookings = json.loads(
            response.read().decode("utf-8")
        )

    summaries = bookings.get("bookingSummaries", [])
    first_booking = summaries[0] if summaries else {}

    return {
        "type": type(bookings).__name__,
        "top_level_keys": list(bookings.keys()),
        "booking_count": len(summaries),
        "first_booking_keys": list(first_booking.keys())
    }
@app.get("/api/travelline/booking-fields")
def travelline_booking_fields():
    return {
        "status": "ok",
        "message": "booking fields endpoint ready"
    }
