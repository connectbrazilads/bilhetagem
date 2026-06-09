from pydantic import BaseModel


class DashboardMetrics(BaseModel):
    prints_today: int
    prints_month: int
    pages_today: int
    pages_month: int
    top_users: list[dict]
    top_printers: list[dict]
    department_usage: list[dict]
    color_usage: list[dict]
    eco_metrics: dict | None = None
