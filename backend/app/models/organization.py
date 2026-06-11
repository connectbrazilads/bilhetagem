from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    billing_plan: Mapped[str] = mapped_column(String(40), default="starter", nullable=False)
    billing_status: Mapped[str] = mapped_column(String(40), default="trial", nullable=False)
    contracted_printer_limit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    agent_enrollment_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_enrollment_token_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    users = relationship("User", back_populates="organization")
    departments = relationship("Department", back_populates="organization")
    printers = relationship("Printer", back_populates="organization")
    print_agents = relationship("PrintAgent", back_populates="organization")
