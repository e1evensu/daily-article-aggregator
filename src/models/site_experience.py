from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class SiteExperience(Base):
    __tablename__ = "site_experiences"

    domain_name: Mapped[str] = mapped_column(String(200), primary_key=True)
    best_strategy: Mapped[str] = mapped_column(String(50))
    rate_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_success: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
