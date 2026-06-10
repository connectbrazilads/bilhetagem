from datetime import datetime

from pydantic import BaseModel, Field


class OperationalHealth(BaseModel):
    agents_total: int = 0
    agents_online: int = 0
    agents_offline: int = 0
    agents_with_alerts: int = 0
    printers_total: int = 0
    printers_monitored: int = 0
    printers_unmonitored: int = 0
    low_toner_printers: int = 0
    unbound_queues: int = 0
    usb_queues: int = 0
    duplicate_queue_aliases: int = 0
    generic_queue_aliases: int = 0
    pending_queue_actions: int = 0
    stale_queue_actions: int = 0


class DashboardContractOverview(BaseModel):
    billing_plan: str = "starter"
    billing_status: str = "trial"
    contracted_printer_limit: int = 0
    active_printers_count: int = 0
    printer_usage_percent: float = 0.0
    printer_limit_status: str = "unlimited"


class DashboardUserUsage(BaseModel):
    username: str
    pages: int = Field(ge=0)
    cost: float = 0.0
    cost_per_page: float = 0.0


class DashboardPrinterUsage(BaseModel):
    printer: str
    pages: int = Field(ge=0)
    cost: float = 0.0
    cost_per_page: float = 0.0


class DashboardDepartmentUsage(BaseModel):
    department: str
    pages: int = Field(ge=0)
    cost: float = 0.0
    cost_per_page: float = 0.0


class DashboardColorUsage(BaseModel):
    type: str
    pages: int = Field(ge=0)
    cost: float = 0.0
    cost_per_page: float = 0.0


class DashboardEcoMetrics(BaseModel):
    pages_saved: int = Field(ge=0)
    co2_saved_g: float = 0.0
    water_saved_l: float = 0.0
    trees_saved: float = 0.0


class DashboardMetrics(BaseModel):
    prints_today: int
    prints_month: int
    pages_today: int
    pages_month: int
    contract_overview: DashboardContractOverview | None = None
    operational_health: OperationalHealth | None = None
    top_users: list[DashboardUserUsage]
    top_printers: list[DashboardPrinterUsage]
    department_usage: list[DashboardDepartmentUsage]
    color_usage: list[DashboardColorUsage]
    eco_metrics: DashboardEcoMetrics | None = None


class MonthlyClosingOrganizationSnapshot(BaseModel):
    id: int
    name: str
    slug: str


class MonthlyClosingContractSnapshot(BaseModel):
    billing_plan: str = "starter"
    billing_status: str = "trial"
    contracted_printer_limit: int = 0
    printers_count: int = 0
    active_printers_count: int = 0
    printer_usage_percent: float = 0.0
    printer_limit_status: str = "unlimited"


class MonthlyClosingPeriodSnapshot(BaseModel):
    year: int
    month: int
    start: str
    end: str


class MonthlyClosingTotalsSnapshot(BaseModel):
    total_jobs: int = 0
    billable_jobs: int = 0
    pending_jobs: int = 0
    pending_pages: int = 0
    pending_cost: float = 0.0
    blocked_jobs: int = 0
    total_pages: int = 0
    mono_pages: int = 0
    color_pages: int = 0
    blocked_pages: int = 0
    blocked_cost: float = 0.0
    total_cost: float = 0.0
    released_jobs: int = 0


class MonthlyClosingUsageSnapshot(BaseModel):
    name: str
    jobs: int = 0
    pages: int = 0
    mono_pages: int = 0
    color_pages: int = 0
    cost: float = 0.0
    cost_per_page: float = 0.0


class MonthlyClosingPolicySnapshot(BaseModel):
    name: str
    action: str = ""
    jobs: int = 0
    billable_jobs: int = 0
    pending_jobs: int = 0
    pending_pages: int = 0
    pending_cost: float = 0.0
    blocked_jobs: int = 0
    blocked_cost: float = 0.0
    pages: int = 0
    mono_pages: int = 0
    color_pages: int = 0
    saved_pages: int = 0
    cost: float = 0.0
    cost_per_page: float = 0.0


class MonthlyClosingEcoSnapshot(BaseModel):
    pages_saved: int = 0
    co2_saved_g: float = 0.0
    water_saved_l: float = 0.0
    trees_saved: float = 0.0


class MonthlyClosingSnapshot(BaseModel):
    organization: MonthlyClosingOrganizationSnapshot
    contract: MonthlyClosingContractSnapshot = Field(default_factory=MonthlyClosingContractSnapshot)
    period: MonthlyClosingPeriodSnapshot
    totals: MonthlyClosingTotalsSnapshot
    by_user: list[MonthlyClosingUsageSnapshot] = Field(default_factory=list)
    by_department: list[MonthlyClosingUsageSnapshot] = Field(default_factory=list)
    by_printer: list[MonthlyClosingUsageSnapshot] = Field(default_factory=list)
    by_type: list[MonthlyClosingUsageSnapshot] = Field(default_factory=list)
    by_policy: list[MonthlyClosingPolicySnapshot] = Field(default_factory=list)
    eco: MonthlyClosingEcoSnapshot


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
    snapshot: MonthlyClosingSnapshot
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
