from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session as Db
from sqlalchemy.orm import joinedload

from ..db import SessionLocal, get_db
from ..models import Event, Season, Series, Session
from ..schemas import EventOut, SeriesDetail, SessionOut, WeekendOut
from ..services.queries import event_out, session_out, sessions_stmt, utc_aware
from ..services.series_visibility import public_only

router = APIRouter()
DbDep = Annotated[Db, Depends(get_db)]


def _split(values: list[str] | None) -> list[str]:
    return [p.strip() for v in values or [] for p in v.split(",") if p.strip()]


def _event_stmt():
    return (
        select(Event).join(Season).join(Series).where(public_only())
        .options(joinedload(Event.season).joinedload(Season.series))
        .order_by(Event.start_date, Event.name)
    )


@router.get("/health")
def health(response: Response) -> dict:
    """Application health only: process is up and the database answers. Data freshness lives in
    /sources/health."""
    try:
        with SessionLocal() as db:
            db.execute(text("select 1"))
    except Exception:
        response.status_code = 503
        return {"status": "unavailable", "database": "down"}
    return {"status": "ok", "database": "up"}


@router.get("/series", response_model=list[SeriesDetail])
def list_series(db: DbDep) -> list[SeriesDetail]:
    now = datetime.now(UTC)
    out = []
    for s in db.scalars(select(Series).where(public_only()).order_by(Series.active.desc(), Series.name)):
        d = SeriesDetail.model_validate(s)
        ev = db.scalars(_event_stmt().where(Series.id == s.id, Event.end_date >= now.date()).limit(1)).unique().first()
        ss = db.scalars(sessions_stmt().where(Series.id == s.id, Session.start_at >= now,
                                              Session.status != "cancelled").limit(1)).first()
        d.next_event = event_out(ev) if ev else None
        d.next_session = session_out(ss) if ss else None
        d.season_year, d.event_count = _season_summary(db, s.id, now.date())
        out.append(d)
    return out


def _season_summary(db: Db, series_id: uuid.UUID, today: date) -> tuple[int | None, int]:
    """(year, events) of the season to show: the one with the next unfinished event, else the latest."""
    rows = list(db.execute(
        select(Season.year, func.count(Event.id), func.max(Event.end_date)).join(Event, Event.season_id == Season.id)
        .where(Season.series_id == series_id).group_by(Season.year).order_by(Season.year)))
    if not rows:
        return None, 0
    current = next((r for r in rows if r[2] >= today), rows[-1])
    return current[0], current[1]


def _series_or_404(db: Db, slug: str) -> Series:
    s = db.scalar(select(Series).where(Series.slug == slug, public_only()))
    if s is None:
        raise HTTPException(404, f"series {slug!r} not found")
    return s


@router.get("/series/{slug}", response_model=SeriesDetail)
def get_series(slug: str, db: DbDep) -> SeriesDetail:
    s = _series_or_404(db, slug)
    now = datetime.now(UTC)
    d = SeriesDetail.model_validate(s)
    ev = db.scalars(_event_stmt().where(Series.id == s.id, Event.end_date >= now.date()).limit(1)).unique().first()
    ss = db.scalars(sessions_stmt().where(Series.id == s.id, Session.start_at >= now,
                                          Session.status != "cancelled").limit(1)).first()
    d.next_event = event_out(ev) if ev else None
    d.next_session = session_out(ss) if ss else None
    d.season_year, d.event_count = _season_summary(db, s.id, now.date())
    return d


@router.get("/series/{slug}/events", response_model=list[EventOut])
def series_events(slug: str, db: DbDep, year: int | None = None, upcoming: bool = False) -> list[EventOut]:
    s = _series_or_404(db, slug)
    stmt = _event_stmt().where(Series.id == s.id)
    if year:
        stmt = stmt.where(Season.year == year)
    if upcoming:
        stmt = stmt.where(Event.end_date >= datetime.now(UTC).date())
    return [event_out(e) for e in db.scalars(stmt).unique()]


@router.get("/events", response_model=list[EventOut])
def list_events(
    db: DbDep,
    series: Annotated[list[str] | None, Query()] = None,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
    limit: Annotated[int, Query(le=500)] = 200,
) -> list[EventOut]:
    stmt = _event_stmt().limit(limit)
    if slugs := _split(series):
        stmt = stmt.where(Series.slug.in_(slugs))
    if from_:
        stmt = stmt.where(Event.end_date >= from_)
    if to:
        stmt = stmt.where(Event.start_date <= to)
    return [event_out(e) for e in db.scalars(stmt).unique()]


@router.get("/events/{event_id}", response_model=EventOut)
def get_event(event_id: uuid.UUID, db: DbDep) -> EventOut:
    e = db.scalars(_event_stmt().where(Event.id == event_id)).unique().first()
    if e is None:
        raise HTTPException(404, "event not found")
    return event_out(e)


@router.get("/events/{event_id}/sessions", response_model=list[SessionOut])
def event_sessions(event_id: uuid.UUID, db: DbDep) -> list[SessionOut]:
    if db.scalars(_event_stmt().where(Event.id == event_id)).unique().first() is None:
        raise HTTPException(404, "event not found")
    return [session_out(s) for s in db.scalars(sessions_stmt().where(Session.event_id == event_id))]


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    db: DbDep,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
    series: Annotated[list[str] | None, Query()] = None,
    session_type: Annotated[list[str] | None, Query()] = None,
    category: str | None = None,
    limit: Annotated[int, Query(le=2000)] = 500,
) -> list[SessionOut]:
    stmt = sessions_stmt().limit(limit)
    if from_:
        stmt = stmt.where(Session.start_at >= utc_aware(from_))
    if to:
        stmt = stmt.where(Session.start_at < utc_aware(to))
    if slugs := _split(series):
        stmt = stmt.where(Series.slug.in_(slugs))
    if types := _split(session_type):
        stmt = stmt.where(Session.session_type.in_(types))
    if category:
        stmt = stmt.where(Series.category == category)
    return [session_out(s) for s in db.scalars(stmt)]


def weekend_window(now: datetime, tz: ZoneInfo) -> tuple[date, date]:
    """Current weekend (Fri-Sun) if today is Fri-Sun, else the upcoming one."""
    today = now.astimezone(tz).date()
    friday = today - timedelta(days=today.weekday() - 4) if today.weekday() >= 4 else today + timedelta(days=4 - today.weekday())
    return friday, friday + timedelta(days=2)


@router.get("/weekend", response_model=WeekendOut)
def weekend(
    db: DbDep,
    tz: str = "UTC",
    at: Annotated[datetime | None, Query(description="override 'now' (testing)")] = None,
    category: str | None = None,
) -> WeekendOut:
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(422, f"unknown timezone {tz!r}") from None
    start, end = weekend_window(utc_aware(at) if at else datetime.now(UTC), zone)
    lo = datetime.combine(start, datetime.min.time(), zone).astimezone(UTC)
    hi = datetime.combine(end + timedelta(days=1), datetime.min.time(), zone).astimezone(UTC)
    stmt = sessions_stmt().where(Session.start_at >= lo, Session.start_at < hi)
    if category:
        stmt = stmt.where(Series.category == category)
    sessions = [session_out(s) for s in db.scalars(stmt)]
    return WeekendOut(start_date=start, end_date=end, timezone=tz, session_count=len(sessions),
                      series_count=len({s.series.slug for s in sessions}), sessions=sessions)



