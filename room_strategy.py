"""
Room Strategy — динамическая стратегия цен для отеля Петровка 17/5.

Модуль рассчитывает рекомендованную цену по категории
в зависимости от загрузки отеля и загрузки конкретной категории.
"""

from typing import Dict, Optional


# ============================================================
# НАСТРОЙКИ ОТЕЛЯ
# ============================================================

HOTEL_NAME = "Петровка 17/5"
TOTAL_ROOMS = 15


# Фактическое количество номеров по категориям
ROOM_CATEGORIES = {
    "Одноместный": {
        "rooms": 2,
        "base_price": 4500,
        "role": "Для деловых гостей и коротких поездок",
    },
    "Стандарт": {
        "rooms": 2,
        "base_price": 5500,
        "role": "Основная категория продаж",
    },
    "Улучшенный": {
        "rooms": 6,
        "base_price": 6200,
        "role": "Категория для повышения среднего чека",
    },
    "Комфорт": {
        "rooms": 5,
        "base_price": 7000,
        "role": "Премиальная категория внутри отеля",
    },
}


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def round_price(price: float) -> int:
    """
    Округление цены до ближайших 100 рублей.
    """

    return int(round(price / 100) * 100)


def get_occupancy_level(occupancy: float) -> str:
    """
    Определяет уровень загрузки отеля.
    """

    if occupancy < 30:
        return "low"

    if occupancy < 50:
        return "moderate"

    if occupancy < 70:
        return "high"

    if occupancy < 85:
        return "very_high"

    return "critical"


def get_occupancy_label(level: str) -> str:
    """
    Человеческое описание уровня загрузки.
    """

    labels = {
        "low": "Низкая загрузка",
        "moderate": "Умеренная загрузка",
        "high": "Высокая загрузка",
        "very_high": "Очень высокая загрузка",
        "critical": "Критически высокая загрузка",
    }

    return labels.get(level, "Не определено")


# ============================================================
# КОЭФФИЦИЕНТ ЦЕНЫ ПО ЗАГРУЗКЕ
# ============================================================

def get_hotel_demand_factor(occupancy: float) -> float:
    """
    Определяет общий коэффициент изменения цены
    в зависимости от загрузки отеля.
    """

    if occupancy < 20:
        return 0.95

    if occupancy < 35:
        return 1.00

    if occupancy < 50:
        return 1.05

    if occupancy < 65:
        return 1.10

    if occupancy < 75:
        return 1.15

    if occupancy < 85:
        return 1.25

    if occupancy < 95:
        return 1.35

    return 1.50


# ============================================================
# СТРАТЕГИЯ КОНКРЕТНОЙ КАТЕГОРИИ
# ============================================================

def calculate_category_strategy(
    category: str,
    occupied_rooms: int,
    total_category_rooms: int,
    hotel_occupancy: float,
    base_price: Optional[float] = None,
) -> Dict:
    """
    Рассчитывает стратегию цены для конкретной категории.
    """

    if category not in ROOM_CATEGORIES:
        raise ValueError(f"Неизвестная категория: {category}")

    category_data = ROOM_CATEGORIES[category]

    if base_price is None:
        base_price = category_data["base_price"]

    # Загрузка конкретной категории
    if total_category_rooms > 0:
        category_occupancy = (
            occupied_rooms / total_category_rooms
        ) * 100
    else:
        category_occupancy = 0

    hotel_level = get_occupancy_level(hotel_occupancy)

    # --------------------------------------------------------
    # Базовый коэффициент от общей загрузки отеля
    # --------------------------------------------------------

    demand_factor = get_hotel_demand_factor(hotel_occupancy)

    # --------------------------------------------------------
    # Дополнительная корректировка по категории
    # --------------------------------------------------------

    category_factor = 1.0

    # Если категория почти распродана —
    # повышаем цену сильнее.
    if category_occupancy >= 90:
        category_factor = 1.20

    elif category_occupancy >= 75:
        category_factor = 1.10

    elif category_occupancy >= 50:
        category_factor = 1.05

    # Если категория почти пустая —
    # не повышаем цену.
    elif category_occupancy < 20:
        category_factor = 0.95

    # --------------------------------------------------------
    # Особая логика для Комфорта
    # --------------------------------------------------------

    if category == "Комфорт":

        if hotel_occupancy >= 65:
            category_factor *= 1.05

        if category_occupancy >= 50:
            category_factor *= 1.05

    # --------------------------------------------------------
    # Рассчитываем цену
    # --------------------------------------------------------

    recommended_price = (
        base_price
        * demand_factor
        * category_factor
    )

    recommended_price = round_price(recommended_price)

    # --------------------------------------------------------
    # Ограничиваем экстремальные изменения
    # --------------------------------------------------------

    minimum_price = base_price * 0.90
    maximum_price = base_price * 1.50

    recommended_price = max(
        recommended_price,
        round_price(minimum_price)
    )

    recommended_price = min(
        recommended_price,
        round_price(maximum_price)
    )

    # --------------------------------------------------------
    # Определяем действие
    # --------------------------------------------------------

    if category_occupancy >= 100:
        action = "STOP"
        action_label = "Категория полностью продана"

    elif category_occupancy >= 90:
        action = "RAISE"
        action_label = "Сильно повышать цену"

    elif category_occupancy >= 75:
        action = "RAISE"
        action_label = "Повышать цену"

    elif hotel_occupancy >= 65:
        action = "HOLD_HIGH"
        action_label = "Держать повышенную цену"

    elif hotel_occupancy < 30:
        action = "SELL"
        action_label = "Стимулировать продажи"

    else:
        action = "HOLD"
        action_label = "Держать текущую стратегию"

    return {
        "category": category,
        "rooms_total": total_category_rooms,
        "rooms_occupied": occupied_rooms,
        "category_occupancy_percent": round(
            category_occupancy,
            1
        ),
        "hotel_occupancy_percent": round(
            hotel_occupancy,
            1
        ),
        "base_price": round_price(base_price),
        "recommended_price": recommended_price,
        "price_change_percent": round(
            (
                recommended_price / base_price - 1
            ) * 100,
            1
        ),
        "action": action,
        "action_label": action_label,
        "demand_level": hotel_level,
        "demand_label": get_occupancy_label(
            hotel_level
        ),
    }


# ============================================================
# СТРАТЕГИЯ НА КОНКРЕТНУЮ ДАТУ
# ============================================================

def calculate_daily_strategy(
    date: str,
    occupied_total: int,
    categories_occupied: Dict[str, int],
) -> Dict:
    """
    Рассчитывает цены всех категорий на конкретную дату.
    """

    hotel_occupancy = (
        occupied_total / TOTAL_ROOMS
    ) * 100

    results = []

    for category, data in ROOM_CATEGORIES.items():

        occupied = categories_occupied.get(
            category,
            0
        )

        result = calculate_category_strategy(
            category=category,
            occupied_rooms=occupied,
            total_category_rooms=data["rooms"],
            hotel_occupancy=hotel_occupancy,
            base_price=data["base_price"],
        )

        results.append(result)

    return {
        "hotel": HOTEL_NAME,
        "date": date,
        "total_rooms": TOTAL_ROOMS,
        "occupied_rooms": occupied_total,
        "free_rooms": TOTAL_ROOMS - occupied_total,
        "hotel_occupancy_percent": round(
            hotel_occupancy,
            1
        ),
        "demand_level": get_occupancy_level(
            hotel_occupancy
        ),
        "demand_label": get_occupancy_label(
            get_occupancy_level(hotel_occupancy)
        ),
        "categories": results,
    }


# ============================================================
# ОБЩАЯ СТРАТЕГИЯ
# ============================================================

def calculate_room_strategy():
    """
    Возвращает общую информацию о категориях отеля.
    """

    recommendations = []

    for category, data in ROOM_CATEGORIES.items():

        recommendations.append({
            "room_type": category,
            "rooms": data["rooms"],
            "base_price": data["base_price"],
            "role": data["role"],
        })

    return {
        "hotel": HOTEL_NAME,
        "total_rooms": TOTAL_ROOMS,
        "room_strategy": recommendations,
        "general_rules": [
            "При росте загрузки сначала повышать цены на Улучшенные и Комфорт.",
            "Стандарт использовать как основную точку входа.",
            "Одноместные номера использовать для деловых гостей и коротких поездок.",
            "При полной продаже категории прекращать её дешёвый тариф.",
            "При загрузке отеля выше 65% переходить к повышенной ценовой стратегии.",
            "При загрузке ниже 30% не завышать цены и стимулировать продажи.",
        ],
    }
