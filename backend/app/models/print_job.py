import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class JobStatus(str, enum.Enum):
    authorized = "authorized"
    blocked = "blocked"
    pending_release = "pending_release"
    released = "released"
    cancelled = "cancelled"


class PrintJob(Base):
    __tablename__ = "print_jobs"
    __table_args__ = (Index("ix_print_jobs_submitted_at", "submitted_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), default=1, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    printer_id: Mapped[int] = mapped_column(ForeignKey("printers.id"), nullable=False)
    printer_alias_id: Mapped[int | None] = mapped_column(ForeignKey("printer_aliases.id"), nullable=True)
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("print_agents.id"), nullable=True)
    external_job_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    document_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    computer_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    queue_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    pages: Mapped[int] = mapped_column(Integer, nullable=False)
    is_color: Mapped[bool] = mapped_column(Boolean, nullable=False)
    cost: Mapped[float] = mapped_column(default=0.0, nullable=False)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    policy_id: Mapped[int | None] = mapped_column(ForeignKey("print_policies.id"), nullable=True)
    policy_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    policy_action: Mapped[str | None] = mapped_column(String(40), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="print_jobs")
    printer = relationship("Printer", back_populates="print_jobs")
    printer_alias = relationship("PrinterAlias")
    agent = relationship("PrintAgent")
    policy = relationship("PrintPolicy")
