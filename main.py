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
