from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class MonthlyClosing(Base):
    __tablename__ = "monthly_closings"
    __table_args__ = (UniqueConstraint("organization_id", "year", "month", name="uq_monthly_closings_org_period"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    total_jobs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    billable_jobs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pending_jobs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    blocked_jobs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_pages: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mono_pages: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    color_pages: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    blocked_pages: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_cost: Mapped[float] = mapped_column(default=0.0, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    organization = relationship("Organization")
