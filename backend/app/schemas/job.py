from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.models.print_job import JobStatus


class PrintJobCreate(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    printer_name: str = Field(min_length=1, max_length=180)
    pages: int = Field(ge=1, le=10000)
    is_color: bool
    external_job_id: str | None = Field(default=None, max_length=120)
    document_name: str | None = Field(default=None, max_length=255)
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PrintJobDecision(BaseModel):
    job_id: int
    status: JobStatus
    authorized: bool
    remaining_pages: int
    remaining_balance: float | None = None
    reason: str | None = None


class PrintJobRead(BaseModel):
    id: int
    username: str
    printer_name: str
    pages: int
    is_color: bool
    status: JobStatus
    reason: str | None
    submitted_at: datetime
    document_name: str | None = None


class JobFilter(BaseModel):
    user_id: int | None = None
    department_id: int | None = None
    printer_id: int | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
