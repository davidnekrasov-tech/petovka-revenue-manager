from pydantic import BaseModel
from datetime import date


class RevenueRecord(BaseModel):
    day: date
    orders: int
    revenue: float
