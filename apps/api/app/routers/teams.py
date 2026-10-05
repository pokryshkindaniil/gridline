from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from gridline_sources import all_sources, supports_entries
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as Db
from sqlalchemy.orm import joinedload, selectinload

from ..db import get_db
from ..models import Event, Season, Series, Team, VehicleEntry, VehicleEntryDriver
from ..schemas import DriverOut, EntryEventOut, EntryOut, SeriesOut, TeamDetail, TeamOut, VehicleOut
from ..services.queries import event_out, is_fixture
from ..services.series_visibility import public_only

router = APIRouter()
DbDep = Annotated[Db, Depends(get_db)]


def _num_key(n: str | None) -> tuple[int, str]:
    return (int(n), "") if n and n.isdigit() else (10_000, n or "")


def resolve_entries(entries: list[VehicleEntry], event_id: uuid.UUID | None) -> list[VehicleEntry]:
    """What is on the grid at an event.

    - If the event has entries from an official entry-list sync, that list is complete: it is the grid.
    - Otherwise season-wide entries, with hand-made event rows replacing the same race number."""
    if event_id is not None:
        listed = [e for e in entries if e.event_id == event_id and e.source_name is not None]
        if listed:
            return sorted(listed, key=lambda e: _num_key(e.race_number))
    base = {e.race_number: e for e in entries if e.event_id is None}
    if event_id is not None:
        for e in entries:
            if e.event_id == event_id:
                base[e.race_number] = e
    return sorted(base.values(), key=lambda e: _num_key(e.race_number))


def build_team(db: Db, team: Team, season_id: uuid.UUID, event_id: uuid.UUID | None = None) -> TeamOut:
    stmt = (
        select(VehicleEntry)
        .where(VehicleEntry.team_id == team.id, VehicleEntry.season_id == season_id,
               or_(VehicleEntry.event_id.is_(None), VehicleEntry.event_id == event_id))
        .options(selectinload(VehicleEntry.drivers).joinedload(VehicleEntryDriver.driver),
                 joinedload(VehicleEntry.manufacturer_ref), joinedload(VehicleEntry.vehicle_model))
    )
    entries = resolve_entries(list(db.scalars(stmt)), event_id)
    out = [
        EntryOut(
            race_number=e.race_number,
            vehicle=vehicle_out(e),
            drivers=[DriverOut.model_validate(d.driver) for d in e.drivers],
        )
        for e in entries
    ]
    sourced = [e for e in entries if e.source_name]
    newest = max(sourced, key=lambda e: e.checked_at or datetime.min.replace(tzinfo=UTC)) if sourced else None
    return TeamOut(
        slug=team.slug, name=team.name, short_name=team.short_name, logo_url=team.logo_url,
        website_url=team.website_url, series=SeriesOut.model_validate(team.series),
        vehicle=out[0].vehicle if out else None, entries=out,
        source_name=newest.source_name if newest else None, source_url=newest.source_url if newest else None,
        checked_at=newest.checked_at if newest else None, is_fixture=is_fixture(newest.source_name) if newest else False,
    )


def vehicle_out(e: VehicleEntry) -> VehicleOut:
    """Canonical names when the entry is linked to a Manufacturer / VehicleModel, else the source spelling."""
    make, model = e.manufacturer_ref, e.vehicle_model
    return VehicleOut(
        manufacturer=make.canonical_name if make else e.manufacturer, manufacturer_slug=make.slug if make else None,
        model=model.canonical_name if model else e.model, model_slug=model.slug if model else None,
        class_name=e.class_name, race_number=e.race_number, image_url=e.image_url,
        fallback_logo_url=e.fallback_logo_url or (make.logo_url if make else None))


def current_season_id(db: Db, series_id: uuid.UUID) -> uuid.UUID | None:
    """Latest season of the series that has any entries."""
    return db.scalar(
        select(Season.id).join(VehicleEntry, VehicleEntry.season_id == Season.id)
        .where(Season.series_id == series_id).order_by(Season.year.desc()).limit(1)
    )


def listed_events(db: Db, series_id: uuid.UUID) -> list[Event]:
    """Events that have an official entry list, in calendar order."""
    return list(db.scalars(
        select(Event).join(Season, Event.season_id == Season.id)
        .options(joinedload(Event.season).joinedload(Season.series))
        .where(Season.series_id == series_id,
               select(VehicleEntry.id).where(VehicleEntry.event_id == Event.id, VehicleEntry.source_name.is_not(None))
               .exists())
        .order_by(Event.start_date)
    ).unique())


def default_event(events: list[Event], today=None) -> Event | None:
    """The next event that has not finished (it has a list), else the most recent one that has a list."""
    if not events:
        return None
    today = today or datetime.now(UTC).date()
    return next((e for e in events if e.end_date >= today), events[-1])


def resolve_event(db: Db, series_id: uuid.UUID, event_id: uuid.UUID | None) -> Event | None:
    if event_id is None:
        return default_event(listed_events(db, series_id))
    event = db.scalar(
        select(Event).join(Season, Event.season_id == Season.id)
        .options(joinedload(Event.season).joinedload(Season.series))
        .where(Event.id == event_id, Season.series_id == series_id)
    )
    if event is None:
        raise HTTPException(404, "event not found in this series")
    return event


@router.get("/series/{slug}/teams", response_model=list[TeamOut])
def series_teams(slug: str, db: DbDep, event_id: uuid.UUID | None = None) -> list[TeamOut]:
    series = db.scalar(select(Series).where(Series.slug == slug, public_only()))
    if series is None:
        raise HTTPException(404, f"series {slug!r} not found")
    event = resolve_event(db, series.id, event_id)
    season_id = event.season_id if event else current_season_id(db, series.id)
    if season_id is None:
        return []
    teams = db.scalars(select(Team).where(Team.series_id == series.id).options(joinedload(Team.series)).order_by(Team.name))
    ev = event.id if event else None
    return [t for t in (build_team(db, tm, season_id, ev) for tm in teams) if t.entries]


@router.get("/series/{slug}/entry-events", response_model=list[EntryEventOut])
def series_entry_events(slug: str, db: DbDep) -> list[EntryEventOut]:
    """Events with an official entry list, each with its provenance. Drives the event picker on the Teams tab."""
    series = db.scalar(select(Series).where(Series.slug == slug, public_only()))
    if series is None:
        raise HTTPException(404, f"series {slug!r} not found")
    events = listed_events(db, series.id)
    chosen = default_event(events)
    entries_url = next((s.entries_url for s in all_sources() if s.series_slug == slug and supports_entries(s)), None)
    out = []
    for ev in events:
        rows = list(db.scalars(select(VehicleEntry).where(VehicleEntry.event_id == ev.id, VehicleEntry.source_name.is_not(None))))
        drivers = db.scalar(
            select(func.count(func.distinct(VehicleEntryDriver.driver_id)))
            .join(VehicleEntry, VehicleEntry.id == VehicleEntryDriver.vehicle_entry_id)
            .where(VehicleEntry.event_id == ev.id, VehicleEntry.source_name.is_not(None))
        ) or 0
        urls = {r.source_url for r in rows}
        newest = max(rows, key=lambda r: r.checked_at or datetime.min.replace(tzinfo=UTC))
        out.append(EntryEventOut(
            event=event_out(ev), competition=next((r.competition for r in rows if r.competition), None),
            entry_count=len(rows), driver_count=drivers, source_name=newest.source_name,
            source_url=urls.pop() if len(urls) == 1 else entries_url, checked_at=newest.checked_at,
            is_fixture=is_fixture(newest.source_name or ""), is_default=ev.id == chosen.id,
        ))
    return out


@router.get("/teams/{slug}", response_model=TeamDetail)
def get_team(slug: str, db: DbDep, event_id: uuid.UUID | None = None, series: str | None = None) -> TeamDetail:
    """A team slug is unique per series ('team-wrt' exists in WEC and GTWC): pass ?series= to pick one."""
    stmt = select(Team).join(Series, Team.series_id == Series.id).where(Team.slug == slug, public_only())
    if series:
        stmt = stmt.where(Series.slug == series)
    team = db.scalar(stmt.order_by(Series.name).options(joinedload(Team.series)))
    if team is None:
        raise HTTPException(404, f"team {slug!r} not found")
    event = resolve_event(db, team.series_id, event_id)
    season_id = event.season_id if event else current_season_id(db, team.series_id)
    base = build_team(db, team, season_id, event.id if event else None) if season_id else TeamOut(
        slug=team.slug, name=team.name, series=SeriesOut.model_validate(team.series), entries=[])
    events = db.scalars(
        select(Event).join(Season).join(Series).options(joinedload(Event.season).joinedload(Season.series))
        .where(Series.id == team.series_id, Event.end_date >= datetime.now(UTC).date())
        .order_by(Event.start_date).limit(5)
    ).unique()
    return TeamDetail(**base.model_dump(), upcoming_events=[event_out(e) for e in events],
                      event=event_out(event) if event else None)

