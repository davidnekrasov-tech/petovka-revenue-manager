# ============================================================
# PRICING / REVENUE MANAGEMENT
# ============================================================

HOTEL_CAPACITY = 15

ROOM_CATEGORIES = {
    "Одноместный стандарт": {
        "capacity": 2,
        "base_price": 5000,
    },
    "Стандартный двухместный номер с одной большой или двумя раздельными кроватями": {
        "capacity": 5,
        "base_price": 5500,
    },
    "Улучшенный номер с большой двуспальной кроватью": {
        "capacity": 6,
        "base_price": 6500,
    },
    "Комфорт с большой двуспальной кроватью": {
        "capacity": 2,
        "base_price": 7500,
    },
}


def get_demand_level(occupancy_percent: float):
    """
    Определяем уровень спроса по общей загрузке гостиницы.
    """

    if occupancy_percent < 30:
        return {
            "level": "low",
            "multiplier": 0.90,
            "recommendation": (
                "Низкая загрузка. Не повышаем цену. "
                "Можно использовать более агрессивную цену "
                "для получения бронирований."
            ),
        }

    if occupancy_percent < 60:
        return {
            "level": "normal",
            "multiplier": 1.00,
            "recommendation": (
                "Нормальная загрузка. "
                "Оставляем базовую цену."
            ),
        }

    if occupancy_percent < 80:
        return {
            "level": "good",
            "multiplier": 1.05,
            "recommendation": (
                "Спрос хороший. "
                "Можно постепенно повышать цены."
            ),
        }

    if occupancy_percent < 90:
        return {
            "level": "high",
            "multiplier": 1.15,
            "recommendation": (
                "Высокая загрузка. "
                "Рекомендуется повысить цены."
            ),
        }

    return {
        "level": "very_high",
        "multiplier": 1.25,
        "recommendation": (
            "Очень высокая загрузка. "
            "Рекомендуется существенно повысить цены."
        ),
    }


def calculate_category_price(
    category_name: str,
    occupied: int,
    hotel_occupancy_percent: float,
):
    """
    Рассчитывает цену конкретной категории
    с учетом фактической загрузки этой категории.
    """

    category = ROOM_CATEGORIES.get(category_name)

    if not category:
        return None

    capacity = category["capacity"]
    base_price = category["base_price"]

    available = max(capacity - occupied, 0)

    if capacity > 0:
        category_occupancy = (occupied / capacity) * 100
    else:
        category_occupancy = 0

    # --------------------------------------------------------
    # Если категория полностью занята
    # --------------------------------------------------------

    if available == 0:

        if category_occupancy >= 100:
            multiplier = 1.25
            recommendation = (
                "Категория полностью продана. "
                "Можно существенно повысить цену."
            )

    # --------------------------------------------------------
    # Категория почти заполнена
    # --------------------------------------------------------

    elif category_occupancy >= 80:

        multiplier = 1.15
        recommendation = (
            "Категория почти заполнена. "
            "Рекомендуется повысить цену."
        )

    # --------------------------------------------------------
    # Хорошая загрузка
    # --------------------------------------------------------

    elif category_occupancy >= 60:

        multiplier = 1.05
        recommendation = (
            "Хорошая загрузка категории. "
            "Можно немного повысить цену."
        )

    # --------------------------------------------------------
    # Средняя загрузка
    # --------------------------------------------------------

    elif category_occupancy >= 30:

        multiplier = 1.00
        recommendation = (
            "Средняя загрузка категории. "
            "Оставляем базовую цену."
        )

    # --------------------------------------------------------
    # Низкая загрузка
    # --------------------------------------------------------

    else:

        multiplier = 0.90
        recommendation = (
            "Низкая загрузка категории. "
            "Можно снизить цену для увеличения продаж."
        )

    # --------------------------------------------------------
    # Дополнительная корректировка по загрузке гостиницы
    # --------------------------------------------------------

    if hotel_occupancy_percent >= 90:

        multiplier = max(multiplier, 1.20)

    elif hotel_occupancy_percent >= 80:

        multiplier = max(multiplier, 1.15)

    # --------------------------------------------------------
    # Расчет цены
    # --------------------------------------------------------

    recommended_price = round(
        base_price * multiplier / 100
    ) * 100

    price_change_percent = round(
        ((recommended_price - base_price) / base_price) * 100
    )

    return {
        "capacity": capacity,
        "occupied": occupied,
        "available": available,
        "category_occupancy_percent": round(
            category_occupancy,
            1
        ),
        "base_price": base_price,
        "recommended_price": recommended_price,
        "price_change_percent": price_change_percent,
        "recommendation": recommendation,
    }


def calculate_prices_from_occupancy(
    target_date: str,
    occupancy_data: dict,
):
    """
    Основной расчет динамической цены.

    occupancy_data должен иметь структуру:

    {
        "rooms": 10,
        "categories": {
            "Одноместный стандарт": 1,
            "Стандартный двухместный номер...": 2,
            "Улучшенный номер...": 6,
            "Комфорт...": 1
        }
    }
    """

    occupied_rooms = int(
        occupancy_data.get("rooms", 0)
    )

    categories_occupancy = occupancy_data.get(
        "categories",
        {}
    )

    # Защита от некорректных значений

    occupied_rooms = max(
        0,
        min(
            occupied_rooms,
            HOTEL_CAPACITY
        )
    )

    available_rooms = (
        HOTEL_CAPACITY - occupied_rooms
    )

    occupancy_percent = round(
        (occupied_rooms / HOTEL_CAPACITY) * 100,
        1
    )

    demand = get_demand_level(
        occupancy_percent
    )

    result_categories = {}

    for category_name, category_data in ROOM_CATEGORIES.items():

        occupied = int(
            categories_occupancy.get(
                category_name,
                0
            )
        )

        # Не позволяем занятости превышать вместимость категории

        occupied = max(
            0,
            min(
                occupied,
                category_data["capacity"]
            )
        )

        result = calculate_category_price(
            category_name=category_name,
            occupied=occupied,
            hotel_occupancy_percent=occupancy_percent,
        )

        result_categories[
            category_name
        ] = result

    return {
        "status": "ok",
        "date": target_date,
        "hotel_capacity": HOTEL_CAPACITY,
        "occupied_rooms": occupied_rooms,
        "available_rooms": available_rooms,
        "occupancy_percent": occupancy_percent,
        "demand_level": demand["level"],
        "multiplier": demand["multiplier"],
        "recommendation": demand["recommendation"],
        "categories": result_categories,
    }


# ============================================================
# GET PRICING FOR ONE DATE
# ============================================================

@app.get("/api/pricing")
def pricing(
    target_date: str,
    occupied_rooms: int,
    category_occupancy: str = "",
):
    """
    Расчет цены на одну дату.

    Пример:

    target_date=2026-10-06
    occupied_rooms=10

    category_occupancy можно передать JSON-строкой.
    """

    import json

    categories = {}

    if category_occupancy:

        try:
            categories = json.loads(
                category_occupancy
            )

        except Exception:

            categories = {}

    occupancy_data = {
        "rooms": occupied_rooms,
        "categories": categories,
    }

    return calculate_prices_from_occupancy(
        target_date=target_date,
        occupancy_data=occupancy_data,
    )


# ============================================================
# FUTURE PRICING
# ============================================================

@app.post("/api/pricing/future")
def future_pricing(data: dict):

    dates = data.get(
        "dates",
        {}
    )

    result = {}

    for date_key, occupancy_data in dates.items():

        result[date_key] = (
            calculate_prices_from_occupancy(
                target_date=date_key,
                occupancy_data=occupancy_data,
            )
        )

    return {
        "status": "ok",
        "dates": result,
    }
