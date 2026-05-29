from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, func
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    domain: Mapped[str] = mapped_column(Enum("security", "ai", "finance", "general", name="domain_enum"))
    type: Mapped[str] = mapped_column(Enum("rss", "api", "github_api", "internal_api", name="source_type_enum"))
    url: Mapped[str] = mapped_column(String(1000))
    auth_mode: Mapped[str] = mapped_column(String(50), default="none")
    fetch_strategy: Mapped[str] = mapped_column(String(50))
    authority: Mapped[str] = mapped_column(Enum("official", "authoritative", "regular", name="authority_enum"))
    status: Mapped[str] = mapped_column(
        Enum("candidate", "trial", "approved", "rejected", "deferred", name="source_status_enum"),
        default="candidate",
    )
    health: Mapped[str] = mapped_column(
        Enum("good", "degraded", "disabled", name="health_enum"),
        default="good",
    )
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_fetch_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_fetch_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
