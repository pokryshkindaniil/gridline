from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.orm import contains_eager

from ..models import Event, Season, Series, Session
from ..schemas import EventOut, SeriesOut, SessionEventRef, SessionOut
from .series_visibility import public_only


def is_fixture(source_name: str) -> bool:
    return "fixture" in source_name.lower()


def sessions_stmt(*, include_hidden: bool = False) -> Select:
    """Sessions with their event/season/series. Sessions of series that are not public are excluded unless a caller
    (tests, dev tooling) asks for them explicitly."""
    stmt = (
        select(Session)
        .join(Event, Session.event_id == Event.id)
        .join(Season, Event.season_id == Season.id)
        .join(Series, Season.series_id == Series.id)
        .options(contains_eager(Session.event).contains_eager(Event.season).contains_eager(Season.series))
        .order_by(Session.start_at, Session.name)
    )
    return stmt if include_hidden else stmt.where(public_only())


def session_out(s: Session) -> SessionOut:
    series = s.event.season.series
    return SessionOut(
        id=s.id,
        event=SessionEventRef.model_validate(s.event),
        series=SeriesOut.model_validate(series),
        name=s.name,
        session_type=s.session_type,
        start_at=s.start_at,
        end_at=s.end_at,
        status=s.status,
        source_url=s.source_url,
        source_name=s.source_name,
        source_updated_at=s.source_updated_at,
        checked_at=s.checked_at,
        is_fixture=is_fixture(s.source_name),
    )


def event_out(e: Event) -> EventOut:
    series = e.season.series
    return EventOut(
        id=e.id, slug=e.slug, name=e.name, series_slug=series.slug, series_short_name=series.short_name,
        year=e.season.year, circuit_name=e.circuit_name, city=e.city, country_code=e.country_code,
        timezone=e.timezone, start_date=e.start_date, end_date=e.end_date, official_url=e.official_url,
        status=e.status,
    )


def utc_aware(dt: datetime) -> datetime:
    from datetime import UTC

    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
