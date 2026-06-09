from datetime import datetime

from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Printer(Base):
    __tablename__ = "printers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)
    location: Mapped[str | None] = mapped_column(String(180), nullable=True)
    is_color: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cost_mono: Mapped[float] = mapped_column(default=0.05, nullable=False)
    cost_color: Mapped[float] = mapped_column(default=0.25, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    toner_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    toner_levels: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    paper_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    page_counter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    print_jobs = relationship("PrintJob", back_populates="printer")
