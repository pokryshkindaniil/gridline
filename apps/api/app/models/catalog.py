from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, utc_col, utcnow, uuid_pk


class Series(Base):
    __tablename__ = "series"
    id: Mapped[uuid.UUID] = uuid_pk()
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    short_name: Mapped[str] = mapped_column(String(40))
    category: Mapped[str] = mapped_column(String(20))
    official_url: Mapped[str] = mapped_column(String(500))
    logo_url: Mapped[str | None] = mapped_column(String(500))
    active: Mapped[bool] = mapped_column(Boolean, default=True)  # has a sync adapter
    # Hidden series keep their data but stay out of listings and feeds.
    public: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Season(Base):
    __tablename__ = "seasons"
    __table_args__ = (UniqueConstraint("series_id", "year"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    series_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"))
    year: Mapped[int] = mapped_column(Integer)
    series: Mapped[Series] = relationship()


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("season_id", "slug", name="uq_events_season_slug"),
        UniqueConstraint("season_id", "external_id", name="uq_events_season_external_id"),
        Index("ix_events_start_date", "start_date"),
        Index("ix_events_season_id_start_date", "season_id", "start_date"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    season_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"))
    external_id: Mapped[str | None] = mapped_column(String(120))  # adapter-provided stable event key
    slug: Mapped[str] = mapped_column(String(160))
    name: Mapped[str] = mapped_column(String(200))
    circuit_name: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(120))
    country_code: Mapped[str | None] = mapped_column(String(2))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    start_date: Mapped[date] = mapped_column(Date)  # local dates at the circuit
    end_date: Mapped[date] = mapped_column(Date)
    official_url: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    season: Mapped[Season] = relationship()
    sessions: Mapped[list[Session]] = relationship(back_populates="event", order_by="Session.start_at")


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        UniqueConstraint("event_id", "external_id"),  # stable identity: never includes start time
        Index("ix_sessions_start_at", "start_at"),
        Index("ix_sessions_event_id_start_at", "event_id", "start_at"),
        Index("ix_sessions_type_start_at", "session_type", "start_at"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    external_id: Mapped[str | None] = mapped_column(String(160))
    name: Mapped[str] = mapped_column(String(200))
    session_type: Mapped[str] = mapped_column(String(20))
    start_at: Mapped[datetime] = utc_col()
    end_at: Mapped[datetime | None] = utc_col(nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    source_url: Mapped[str] = mapped_column(String(500))
    source_name: Mapped[str] = mapped_column(String(200))
    source_updated_at: Mapped[datetime | None] = utc_col(nullable=True)
    checked_at: Mapped[datetime] = utc_col(default=utcnow)
    fingerprint: Mapped[str] = mapped_column(String(64))
    sequence: Mapped[int] = mapped_column(Integer, default=0)  # iCalendar SEQUENCE
    created_at: Mapped[datetime] = utc_col(default=utcnow)
    updated_at: Mapped[datetime] = utc_col(default=utcnow)  # last *real* change (LAST-MODIFIED)
    event: Mapped[Event] = relationship(back_populates="sessions")


class SessionChange(Base):
    __tablename__ = "session_changes"
    __table_args__ = (
        Index("ix_session_changes_session_id_detected_at", "session_id", "detected_at"),
        Index("ix_session_changes_detected_at", "detected_at"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id", ondelete="RESTRICT"))  # history is never cascaded away
    detected_at: Mapped[datetime] = utc_col(default=utcnow)
    field_name: Mapped[str] = mapped_column(String(40))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(String(500))
    session: Mapped[Session] = relationship()
