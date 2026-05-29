from datetime import date, datetime

from sqlalchemy import Date, DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.mysql import JSON, MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class Digest(Base):
    __tablename__ = "digests"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    date: Mapped[date] = mapped_column(Date)
    domain: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    stats_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    highlights_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    content_markdown: Mapped[str] = mapped_column(MEDIUMTEXT)
    oss_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (UniqueConstraint("date", "domain", name="uq_date_domain"),)
