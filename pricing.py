from datetime import date
from typing import Dict, Any


# ============================================================
# PETROVKA 17/5 — PRICING ENGINE
# ============================================================

HOTEL_CAPACITY = 15

# Количество номеров по категориям.
# Если фактическое количество отличается — поменяем здесь.
ROOM_CAPACITY = {
    "Одноместный стандарт": 2,
    "Стандартный двухместный номер с одной большой или двумя раздельными кроватями": 5,
    "Улучшенный номер с большой двуспальной кроватью": 6,
    "Комфорт с большой двуспальной кроватью": 2,
}


# Базовые цены.
# Это стартовые значения.
# После накопления статистики TravelLine
# алгоритм будем корректировать автоматически.
BASE_PRICES = {
    "Одноместный стандарт": 5000,
    "Стандартный двухместный номер с одной большой или двумя раздельными кроватями": 5500,
    "Улучшенный номер с большой двуспальной кроватью": 6500,
    "Комфорт с большой двуспальной кроватью": 7500,
}


def get_demand_level(occupancy_percent: float) -> str:
    """
    Определяет уровень спроса по общей загрузке.
    """

    if occupancy_percent < 30:
        return "low"

    if occupancy_percent < 50:
        return "normal"

    if occupancy_percent < 70:
        return "good"

    if occupancy_percent < 85:
        return "high"

    if occupancy_percent < 95:
        return "very_high"

    return "sold_out_risk"


def get_price_multiplier(occupancy_percent: float) -> float:
    """
    Коэффициент изменения цены в зависимости от загрузки.
    """

    if occupancy_percent < 30:
        return 0.90

    if occupancy_percent < 50:
        return 1.00

    if occupancy_percent < 70:
        return 1.05

    if occupancy_percent < 85:
        return 1.10

    if occupancy_percent < 95:
        return 1.20

    return 1.35


def round_price(price: float) -> int:
    """
    Округляем цену до 100 рублей.
    """

    return int(round(price / 100) * 100)


def calculate_prices(
    target_date: str,
    occupied_rooms: int,
    category_occupancy: Dict[str, int] | None = None,
) -> Dict[str, Any]:

    if category_occupancy is None:
        category_occupancy = {}

    # --------------------------------------------------------
    # Общая загрузка
    # --------------------------------------------------------

    occupancy_percent = (
        occupied_rooms / HOTEL_CAPACITY
    ) * 100

    demand_level = get_demand_level(occupancy_percent)

    multiplier = get_price_multiplier(occupancy_percent)

    available_rooms = max(
        HOTEL_CAPACITY - occupied_rooms,
        0
    )

    # --------------------------------------------------------
    # Цены по категориям
    # --------------------------------------------------------

    categories = {}

    for category, capacity in ROOM_CAPACITY.items():

        occupied_in_category = category_occupancy.get(
            category,
            0
        )

        available_in_category = max(
            capacity - occupied_in_category,
            0
        )

        base_price = BASE_PRICES[category]

        recommended_price = round_price(
            base_price * multiplier
        )

        categories[category] = {
            "capacity": capacity,
            "occupied": occupied_in_category,
            "available": available_in_category,
            "base_price": base_price,
            "recommended_price": recommended_price,
            "price_change_percent": round(
                (multiplier - 1) * 100
            ),
        }

    # --------------------------------------------------------
    # Рекомендация
    # --------------------------------------------------------

    if occupancy_percent < 30:

        recommendation = (
            "Низкая загрузка. "
            "Не повышаем цену. "
            "Можно использовать более агрессивную цену "
            "для получения бронирований."
        )

    elif occupancy_percent < 50:

        recommendation = (
            "Нормальная загрузка. "
            "Оставляем базовую цену и наблюдаем "
            "за темпом продаж."
        )

    elif occupancy_percent < 70:

        recommendation = (
            "Спрос хороший. "
            "Можно постепенно повышать цены."
        )

    elif occupancy_percent < 85:

        recommendation = (
            "Высокий спрос. "
            "Рекомендуется повышение цены."
        )

    elif occupancy_percent < 95:

        recommendation = (
            "Очень высокая загрузка. "
            "Нужно защищать остаток номерного фонда "
            "и повышать цену."
        )

    else:

        recommendation = (
            "Высокий риск полной загрузки. "
            "Рекомендуется максимальная цена."
        )

    return {
        "status": "ok",
        "date": target_date,
        "hotel_capacity": HOTEL_CAPACITY,
        "occupied_rooms": occupied_rooms,
        "available_rooms": available_rooms,
        "occupancy_percent": round(
            occupancy_percent,
            1
        ),
        "demand_level": demand_level,
        "multiplier": multiplier,
        "recommendation": recommendation,
        "categories": categories,
    }


def calculate_future_prices(
    dates: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:

    result = {}

    for target_date, data in dates.items():

        occupied_rooms = data.get(
            "rooms",
            0
        )

        category_occupancy = data.get(
            "categories",
            {}
        )

        result[target_date] = calculate_prices(
            target_date=target_date,
            occupied_rooms=occupied_rooms,
            category_occupancy=category_occupancy,
        )

    return {
        "status": "ok",
        "dates": result,
    }
