from analytics import calculate_analytics
from recommendations import generate_recommendations
from hotel_knowledge import hotel_info
from room_strategy import calculate_room_strategy


def generate_ai_report():

    analytics = calculate_analytics()

    recommendations = generate_recommendations()

    room_strategy = calculate_room_strategy()


    summary = (
        f"Отель {hotel['name']} работает в категории {hotel['category']}. "
        f"Средняя дневная выручка составляет "
        f"{analytics['average_daily_revenue']} RUB. "
        f"Лучший день по выручке: {analytics['best_day']}."
    )


    insights = [

        f"Общее количество заказов: {analytics['total_orders']}",

        f"Лучший результат за день: "
        f"{analytics['best_day_revenue']} RUB",

        f"Рост выручки: "
        f"{analytics['growth_percent']}%"

    ]


    actions = recommendations["recommendations"]


    return {

        "hotel": hotel["name"],

        "summary": summary,

        "insights": insights,

        "actions": actions,

        "positioning": hotel["positioning"],

        "advantages": hotel["advantages"],

        "limitations": hotel["limitations"],

        "room_strategy": room_strategy

    }
