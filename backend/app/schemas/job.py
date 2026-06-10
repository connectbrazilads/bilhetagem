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
    agent_uid: str | None = Field(default=None, max_length=120)
    computer_name: str | None = Field(default=None, max_length=180)
    queue_name: str | None = Field(default=None, max_length=180)
    printer_driver_name: str | None = Field(default=None, max_length=180)
    printer_port_name: str | None = Field(default=None, max_length=180)
    printer_connection_type: str | None = Field(default=None, max_length=40)
    printer_ip_address: str | None = Field(default=None, max_length=45)
    printer_serial: str | None = Field(default=None, max_length=80)
    printer_device_id: str | None = Field(default=None, max_length=255)
    printer_fingerprint: str | None = Field(default=None, max_length=255)


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
    user_full_name: str | None = None
    department_id: int | None = None
    department_name: str | None = None
    printer_name: str
    pages: int
    is_color: bool
    cost: float
    status: JobStatus
    reason: str | None
    submitted_at: datetime
    document_name: str | None = None
    computer_name: str | None = None
    queue_name: str | None = None
    policy_name: str | None = None
    policy_action: str | None = None


class JobFilter(BaseModel):
    user_id: int | None = None
    department_id: int | None = None
    printer_id: int | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
