from datetime import datetime

from sqlalchemy import DateTime, Enum, Index, Integer, String, Text, func
from sqlalchemy.dialects.mysql import JSON, MEDIUMTEXT, TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class Item(Base):
    __tablename__ = "items"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    domain: Mapped[str] = mapped_column(Enum("security", "ai", "finance", "general", name="domain_enum"))
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(500))
    canonical_url: Mapped[str] = mapped_column(String(1000))
    content_text: Mapped[str | None] = mapped_column(MEDIUMTEXT, nullable=True)
    author: Mapped[str | None] = mapped_column(String(200), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    dedup_hash: Mapped[str] = mapped_column(String(64), unique=True)
    also_seen_in: Mapped[list | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Stage 1
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    summary_zh: Mapped[str | None] = mapped_column(String(500), nullable=True)
    insight_score: Mapped[int | None] = mapped_column(TINYINT(unsigned=True), nullable=True)
    credibility: Mapped[str] = mapped_column(
        Enum("high", "medium", "low", "unknown", name="credibility_enum"),
        default="unknown",
    )

    # Stage 2
    confidence: Mapped[str | None] = mapped_column(
        Enum("tentative", "firm", "confirmed", name="confidence_enum"),
        nullable=True,
    )
    recommendation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    trend_signal: Mapped[str | None] = mapped_column(
        Enum("emerging", "growing", "stable", "declining", name="trend_signal_enum"),
        nullable=True,
    )
    action_suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Analysis metadata
    analysis_stage: Mapped[int] = mapped_column(TINYINT, default=0)
    stage1_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    stage1_provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    stage1_prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    stage1_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    stage1_error: Mapped[str | None] = mapped_column(String(200), nullable=True)
    stage2_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    stage2_provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    stage2_prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    stage2_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    stage2_error: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Retention
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_domain_score", "domain", insight_score.desc()),
        Index("ix_domain_published", "domain", "published_at"),
    )
