from fastapi import FastAPI
from datetime import datetime

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


@app.get("/api/revenue")
def revenue():
    return {
        "currency": "RUB",
        "today_revenue": 0,
        "message": "Revenue data endpoint ready"
    }


@app.get("/api/forecast")
def forecast():
    return {
        "forecast": [],
        "message": "Forecast module ready"
    }


@app.get("/api/recommendations")
def recommendations():
    return {
        "recommendations": [],
        "message": "Recommendation engine ready"
    }
