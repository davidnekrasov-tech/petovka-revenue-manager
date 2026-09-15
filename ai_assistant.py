from analytics import calculate_analytics
from recommendations import generate_recommendations
from forecast import calculate_forecast
from hotel_knowledge import get_hotel_info


def generate_ai_report():

    analytics = calculate_analytics()
    recommendations = generate_recommendations()
    forecast = calculate_forecast()
    hotel_info = get_hotel_info()


    summary = (
        f"Отель {hotel_info['name']} — "
        f"{hotel_info['category']} в центре Москвы. "
        f"Средняя дневная выручка составляет "
        f"{analytics['average_daily_revenue']} RUB. "
        f"Лучший день по выручке: "
        f"{analytics['best_day']}."
    )


    insights = [
        f"Всего заказов: {analytics['total_orders']}",
        f"Лучший результат за день: "
        f"{analytics['best_day_revenue']} RUB",
        f"Прогноз на следующий день: "
        f"{forecast['forecast_next_day']} RUB"
    ]


    actions = recommendations["recommendations"]


    return {

        "hotel": {
            "name": hotel_info["name"],
            "address": hotel_info["address"],
            "category": hotel_info["category"]
        },


        "summary": summary,


        "insights": insights,


        "actions": actions,


        "services": {
            "breakfast": hotel_info["services"]["breakfast"],
            "pets": hotel_info["services"]["pets"]
        },


        "strengths": hotel_info["service"]["strengths"],


        "advantages": hotel_info["location"]["advantages"],


        "limitations": hotel_info["design"]["limitations"],


        "positioning": hotel_info["communication_rules"]["main_message"]

    }
