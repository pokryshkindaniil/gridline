from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, PrimaryKeyConstraint, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, utc_col, utcnow, uuid_pk
from .catalog import Series


class CalendarFeed(Base):
    __tablename__ = "calendar_feeds"
    id: Mapped[uuid.UUID] = uuid_pk()
    public_token: Mapped[str] = mapped_column(String(32), unique=True)
    edit_token_hash: Mapped[str] = mapped_column(String(64))  # sha256 of the secret edit token
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    include_emoji: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = utc_col(default=utcnow)
    updated_at: Mapped[datetime] = utc_col(default=utcnow)
    revoked_at: Mapped[datetime | None] = utc_col(nullable=True)
    series: Mapped[list[Series]] = relationship(secondary="calendar_feed_series", order_by=Series.name)
    session_types: Mapped[list[CalendarFeedSessionType]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )


class CalendarFeedSeries(Base):
    __tablename__ = "calendar_feed_series"
    __table_args__ = (PrimaryKeyConstraint("feed_id", "series_id"),)
    feed_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("calendar_feeds.id", ondelete="CASCADE"))
    series_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"))


class CalendarFeedSessionType(Base):
    __tablename__ = "calendar_feed_session_types"
    __table_args__ = (PrimaryKeyConstraint("feed_id", "session_type"),)
    feed_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("calendar_feeds.id", ondelete="CASCADE"))
    session_type: Mapped[str] = mapped_column(String(20))


class SourceRun(Base):
    __tablename__ = "source_runs"
    __table_args__ = (Index("ix_source_runs_source_id_started_at", "source_id", "started_at"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    source_id: Mapped[str] = mapped_column(String(60))
    mode: Mapped[str] = mapped_column(String(10), default="live")  # live | fixture
    kind: Mapped[str] = mapped_column(String(10), default="schedule", server_default="schedule")  # schedule | entries
    started_at: Mapped[datetime] = utc_col(default=utcnow)
    completed_at: Mapped[datetime | None] = utc_col(nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="running")  # running | success | partial | failed
    records_seen: Mapped[int] = mapped_column(Integer, default=0)
    records_changed: Mapped[int] = mapped_column(Integer, default=0)
    issues: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # quarantined events / warnings
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)


class SyncLease(Base):
    """Cross-process "one sync at a time" lease (see app.services.lease).

    A row per lock name. A runner owns the lease while `owner_token` is its token and `expires_at` is in the future;
    it renews `expires_at` with short transactions. A crashed runner simply stops renewing: after `expires_at` the next
    runner takes over, with no manual intervention. Survives connection churn (unlike a session advisory lock)."""

    __tablename__ = "sync_leases"
    name: Mapped[str] = mapped_column(String(80), primary_key=True)
    owner_token: Mapped[str] = mapped_column(String(64))
    acquired_at: Mapped[datetime] = utc_col()
    heartbeat_at: Mapped[datetime] = utc_col()
    expires_at: Mapped[datetime] = utc_col()
