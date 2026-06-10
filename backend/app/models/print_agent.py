from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class PrintAgent(Base):
    __tablename__ = "print_agents"
    __table_args__ = (UniqueConstraint("organization_id", "agent_uid", name="uq_print_agents_org_uid"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), default=1, nullable=False)
    agent_uid: Mapped[str] = mapped_column(String(120), nullable=False)
    computer_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    os_user: Mapped[str | None] = mapped_column(String(120), nullable=True)
    version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    capture_mode: Mapped[str | None] = mapped_column(String(40), nullable=True)
    event_log_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    auto_update_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    organization = relationship("Organization", back_populates="print_agents")
    aliases = relationship("PrinterAlias", back_populates="agent")
