import enum
from datetime import datetime, time

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Time, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class PolicyRuleType(str, enum.Enum):
    always = "always"
    max_pages = "max_pages"
    color = "color"
    time_window = "time_window"


class PolicyAction(str, enum.Enum):
    allow = "allow"
    block = "block"
    require_release = "require_release"
    force_mono = "force_mono"


class PrintPolicy(Base):
    __tablename__ = "print_policies"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_print_policies_org_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), default=1, nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    rule_type: Mapped[PolicyRuleType] = mapped_column(Enum(PolicyRuleType), nullable=False)
    action: Mapped[PolicyAction] = mapped_column(Enum(PolicyAction), nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    printer_id: Mapped[int | None] = mapped_column(ForeignKey("printers.id"), nullable=True)
    printer_alias_id: Mapped[int | None] = mapped_column(ForeignKey("printer_aliases.id"), nullable=True)
    queue_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    max_pages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    days_of_week: Mapped[str | None] = mapped_column(String(40), nullable=True)
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    message: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    organization = relationship("Organization")
    user = relationship("User")
    department = relationship("Department")
    printer = relationship("Printer")
    printer_alias = relationship("PrinterAlias")
