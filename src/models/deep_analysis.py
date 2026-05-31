from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.mysql import JSON, MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class DeepAnalysis(Base):
    """A research-grade deep-dive report for one subject (e.g. a security
    advisory). Produced by the pi Finder stage; `report_md` holds the full
    code-grounded RCA. Linked back to the source `items` row via `item_id`
    when the deep-dive was triggered by the daily pipeline."""

    __tablename__ = "deep_analyses"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    subject: Mapped[str] = mapped_column(String(128), index=True)
    item_id: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(32), default="vuln_rca")
    repo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vuln_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fix_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempt_count: Mapped[int] = mapped_column(default=0)
    attempts: Mapped[list | None] = mapped_column(JSON, nullable=True)
    report_md: Mapped[str | None] = mapped_column(MEDIUMTEXT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
