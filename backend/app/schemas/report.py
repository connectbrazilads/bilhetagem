from datetime import datetime

from pydantic import BaseModel, Field


class DashboardMetrics(BaseModel):
    prints_today: int
    prints_month: int
    pages_today: int
    pages_month: int
    operational_health: dict | None = None
    top_users: list[dict]
    top_printers: list[dict]
    department_usage: list[dict]
    color_usage: list[dict]
    eco_metrics: dict | None = None


class MonthlyClosingCreate(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)


class MonthlyClosingRead(BaseModel):
    id: int
    year: int
    month: int
    total_jobs: int
    billable_jobs: int
    pending_jobs: int
    blocked_jobs: int
    total_pages: int
    mono_pages: int
    color_pages: int
    blocked_pages: int
    total_cost: float
    snapshot: dict
    generated_at: datetime

    model_config = {"from_attributes": True}


class MonthlyClosingEmailRequest(BaseModel):
    recipients: str | None = Field(default=None, max_length=255)
    include_pdf: bool | None = None
    include_xlsx: bool | None = None


class MonthlyClosingEmailRead(BaseModel):
    sent: bool
    recipients: list[str]
    attachments: list[str]


class MonthlyClosingDueEmailRead(BaseModel):
    sent: bool
    reason: str | None = None
    period: str | None = None
    closing_id: int | None = None
    recipients: list[str] = Field(default_factory=list)
    attachments: list[str] = Field(default_factory=list)
