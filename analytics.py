from data import revenue_data


def calculate_analytics():
    total_revenue = sum(item.revenue for item in revenue_data)
    total_orders = sum(item.orders for item in revenue_data)

    days_count = len(revenue_data)

    average_daily_revenue = 0
    if days_count:
        average_daily_revenue = total_revenue / days_count

    best_day = max(
        revenue_data,
        key=lambda item: item.revenue
    )

    growth_percent = 0

    if len(revenue_data) >= 2:
        first_day = revenue_data[0].revenue
        last_day = revenue_data[-1].revenue

        if first_day:
            growth_percent = (
                (last_day - first_day) / first_day
            ) * 100

    return {
        "average_daily_revenue": round(
            average_daily_revenue, 2
        ),
        "best_day": str(best_day.day),
        "best_day_revenue": best_day.revenue,
        "growth_percent": round(
            growth_percent, 2
        ),
        "total_orders": total_orders
    }
