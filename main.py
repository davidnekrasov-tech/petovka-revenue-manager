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
    import json
    import os
    from urllib.parse import urlencode, quote
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
    first_number = summaries[0]["number"] if summaries else None

    if not first_number:
        return {
            "status": "ok",
            "message": "No bookings found"
        }

    detail_request = Request(
        "https://partner.tlintegration.com/api/read-reservation/v1/properties/4950/bookings/"
        + quote(first_number),
        headers={
            "Authorization": f"Bearer {access_token}"
        },
        method="GET",
    )

    with urlopen(detail_request, timeout=20) as response:
        details = json.loads(
            response.read().decode("utf-8")
        )

    booking = details.get("booking", {})
    room_stays = booking.get("roomStays", [])
    first_room_stay = room_stays[0] if room_stays else {}

    return {
    "status": "ok",
    "booking_number": booking.get("number"),
    "booking_status": booking.get("status"),
    "currency": booking.get("currencyCode"),

    "stay_dates": first_room_stay.get("stayDates"),
    "room_type": first_room_stay.get("roomType"),
    "guest_count": first_room_stay.get("guestCount"),
    "daily_rates": first_room_stay.get("dailyRates"),
    "room_total": first_room_stay.get("total"),

    "booking_total": booking.get("total"),
    "source": booking.get("source"),
    "services": booking.get("services"),
}
@app.get("/api/travelline/latest-booking")
def travelline_latest_booking():
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

    if not summaries:
        return {
            "status": "ok",
            "booking_found": False
        }

    latest = max(
        summaries,
        key=lambda booking: booking.get(
            "createdDateTime",
            ""
        )
    )

    return {
        "status": "ok",
        "booking_found": True,
        "latest_booking": latest
    }
@app.get("/api/travelline/recent-bookings")
def travelline_recent_bookings():
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
        "https://partner.tlintegration.com/api/read-reservation/v1/properties/4950/bookings?count=100&lastModification=2026-09-16T00:00:00Z",
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
        "status": "ok",
        "booking_count": len(summaries),
        "has_more_data": bookings.get("hasMoreData"),
        "bookings": summaries
    }
@app.get("/api/travelline/recent-booking-details")
def travelline_recent_booking_details():
    import json
    import os
    import time
    from urllib.parse import urlencode, quote
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError

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
        "https://partner.tlintegration.com/api/read-reservation/v1/properties/4950/bookings?count=100&lastModification=2026-09-16T00:00:00Z",
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

    results = []

    for summary in summaries:

        if summary.get("status") != "Active":
            continue

        number = summary.get("number")

        if not number:
            continue

        # защита от ограничения TravelLine 429
        time.sleep(1)

        detail_request = Request(
            "https://partner.tlintegration.com/api/read-reservation/v1/properties/4950/bookings/"
            + quote(number),
            headers={
                "Authorization": f"Bearer {access_token}"
            },
            method="GET",
        )

        try:
            with urlopen(detail_request, timeout=20) as response:
                details = json.loads(
                    response.read().decode("utf-8")
                )

            booking = details.get("booking", {})
            room_stays = booking.get("roomStays", [])

            results.append({
                "number": booking.get("number"),
                "status": booking.get("status"),
                "currency": booking.get("currencyCode"),
                "room_stays": room_stays,
                "total": booking.get("total"),
                "source": booking.get("source"),
            })

        except HTTPError as e:
            results.append({
                "number": number,
                "error": "HTTPError",
                "message": str(e)
            })

        except Exception as e:
            results.append({
                "number": number,
                "error": type(e).__name__,
                "message": str(e)
            })


    return {
        "status": "ok",
        "active_booking_count": len(results),
        "bookings": results
    }
