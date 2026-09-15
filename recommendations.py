from data import revenue_data


def generate_recommendations():
    total_orders = sum(item.orders for item in revenue_data)
    total_revenue = sum(item.revenue for item in revenue_data)

    if total_orders == 0:
        return {
            "recommendations": [
                "Недостаточно данных для анализа"
            ]
        }

    average_check = total_revenue / total_orders

    recommendations = []

    if average_check < 4000:
        recommendations.append(
            "Рекомендуется увеличить средний чек через дополнительные услуги"
        )
    else:
        recommendations.append(
            "Средний чек находится на хорошем уровне"
        )

    best_day = max(
        revenue_data,
        key=lambda x: x.revenue
    )

    recommendations.append(
        f"Лучший день по выручке: {best_day.day}"
    )

    recommendations.append(
        "Рекомендуется повышать цены в дни высокого спроса"
    )

    return {
        "average_check": round(average_check, 2),
        "recommendations": recommendations
    }
