from data import revenue_data


def calculate_forecast():
    revenues = [item.revenue for item in revenue_data]

    if not revenues:
        return {
            "forecast": 0,
            "message": "No data available"
        }

    average = sum(revenues) / len(revenues)

    return {
        "forecast_next_day": round(average, 2),
        "currency": "RUB",
        "based_on_days": len(revenues),
        "message": "Forecast calculated"
    }
