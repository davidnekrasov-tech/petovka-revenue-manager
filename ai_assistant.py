from data import revenue_data
from analytics import calculate_analytics
from recommendations import generate_recommendations
from forecast import calculate_forecast


def generate_ai_report():
    analytics = calculate_analytics()
    recommendations = generate_recommendations()
    forecast = calculate_forecast()

    summary = (
        f"Средняя дневная выручка составляет "
        f"{analytics['average_daily_revenue']} RUB. "
        f"Лучший день по выручке: "
        f"{analytics['best_day']}. "
    )

    insights = [
        f"Общая сумма заказов: {analytics['total_orders']}",
        f"Лучший результат за день: {analytics['best_day_revenue']} RUB",
        f"Прогноз на следующий день: {forecast['forecast_next_day']} RUB"
    ]

    actions = recommendations["recommendations"]

    return return {
    "hotel": hotel["name"],
    "summary": summary,
    "insights": insights,
    "actions": actions,
    "positioning": hotel["positioning"],
    "advantages": hotel["advantages"],
    "limitations": hotel["limitations"]
}
