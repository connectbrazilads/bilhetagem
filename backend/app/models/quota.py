from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Quota(Base):
    __tablename__ = "quotas"
    __table_args__ = (UniqueConstraint("user_id", "year", "month", name="uq_quota_user_month"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    monthly_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    used_pages: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    monthly_balance: Mapped[float] = mapped_column(default=50.0, nullable=False)
    used_balance: Mapped[float] = mapped_column(default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user = relationship("User", back_populates="quotas")

    @property
    def remaining_pages(self) -> int:
        return max(self.monthly_limit - self.used_pages, 0)

    @property
    def remaining_balance(self) -> float:
        return max(self.monthly_balance - self.used_balance, 0.0)
