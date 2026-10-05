"""Entry-list diff/update engine: parsed entries -> database.

Identity: an entry is (season, event, race number). Within one event the list is authoritative and complete, so a
sync of an event makes the stored entries equal to the list:

  same number, anything else changed -> the entry is updated in place (team, car, class, drivers, order)
  number not in the list any more    -> removed (a renumbered car is a removal plus an insertion)
  number new in the list             -> inserted

Other events are never touched: the same car legitimately has a different crew at every event.

A season-wide roster (`event_external_id=None`, e.g. Formula 1) is the same idea one level up: it is identified by
(team, race number) among the season's roster rows (event_id NULL) of the teams the source listed. It adopts the
development-seed rows of those teams (same number) instead of duplicating them, and removes seed/stale rows of
those teams that the official list does not contain.

Names are never stored from the source blindly: teams, drivers, manufacturers and models go through
`services.identity.Resolver` (source-aware aliases, no fuzzy merging). The exact source spelling of manufacturer and
model stays on the entry row as provenance.

Safety (same philosophy as the schedule engine):
  - an event is only applied when the parser read it completely (per-event quarantine happens in the parser)
  - an event whose list shrinks below EVENT_SHRINK_RATIO of the stored one is left exactly as stored (warning)
  - a fixture never overwrites entries that came from a live source
  - one event failing inside the database never aborts the others (savepoint per event)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from gridline_sources import ParsedEntry
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..models import Event, Season, Series, VehicleEntry, VehicleEntryDriver
from .identity import Resolver
from .queries import is_fixture

log = logging.getLogger(__name__)

EVENT_SHRINK_RATIO = 0.5


@dataclass
class EntryStats:
    seen: int = 0
    events_applied: int = 0
    inserted: int = 0
    updated: int = 0
    removed: int = 0
    warnings: list[str] = field(default_factory=list)
    changes: list[str] = field(default_factory=list)  # human-readable, e.g. "barcelona #12: drivers A, B -> A, C"

    @property
    def changed(self) -> int:
        return self.inserted + self.updated + self.removed


def _names(slugs: list[str]) -> str:
    return ", ".join(slugs) or "-"


def _upsert_values(r: Resolver, series: Series, p: ParsedEntry, source_name: str) -> dict:
    make = r.manufacturer(p.manufacturer)
    model = r.vehicle_model(make, p.model, class_name=p.class_name, source_name=source_name, source_url=p.source_url)
    if model is not None and series.category == "formula" and model.season_year is None:
        model.season_year = p.season_year
    return dict(manufacturer=p.manufacturer, model=p.model, class_name=p.class_name, competition=p.competition,
                manufacturer_id=make.id if make else None, vehicle_model_id=model.id if model else None)


def _diff_row(row: VehicleEntry, new_vals: dict, team, have, want) -> list[str]:
    diffs = []
    for fld, label in (("manufacturer", "make"), ("model", "model"), ("class_name", "class"), ("competition", "cup")):
        if getattr(row, fld) != new_vals[fld]:
            diffs.append(f"{label} {getattr(row, fld)} -> {new_vals[fld]}")
    if row.team_id != team.id:
        diffs.append(f"team -> {team.name}")
    if [d.id for d in have] != [d.id for d in want]:
        diffs.append(f"drivers {_names([d.slug for d in have])} -> {_names([d.slug for d in want])}")
    return diffs


def _sync_drivers(row: VehicleEntry, want) -> None:
    have_by_id = {d.driver_id: d for d in row.drivers}
    want_ids = {d.id for d in want}
    for link in list(row.drivers):
        if link.driver_id not in want_ids:
            row.drivers.remove(link)
    for pos, drv in enumerate(want):
        link = have_by_id.get(drv.id)
        if link is None:
            row.drivers.append(VehicleEntryDriver(driver_id=drv.id, position=pos, role="driver"))
        else:
            link.position = pos


def _upsert(db: DbSession, r: Resolver, series: Series, row: VehicleEntry | None, p: ParsedEntry, *, season: Season,
            event: Event | None, source_name: str, now: datetime, stats: EntryStats, label: str) -> VehicleEntry:
    team = r.team(p.team_name, p.team_external_id, p.team_aliases)
    want = [r.driver(d) for d in p.drivers]
    new_vals = _upsert_values(r, series, p, source_name)
    if row is None:
        row = VehicleEntry(season_id=season.id, event_id=event.id if event else None, race_number=p.race_number,
                           team_id=team.id, source_name=source_name, source_url=p.source_url, checked_at=now, **new_vals)
        row.drivers = [VehicleEntryDriver(driver_id=drv.id, position=pos, role="driver") for pos, drv in enumerate(want)]
        db.add(row)
        db.flush()
        stats.inserted += 1
        stats.changes.append(f"{label} #{p.race_number}: added ({team.name}; {_names([d.slug for d in want])})")
        return row

    have = [d.driver for d in sorted(row.drivers, key=lambda x: x.position)]
    diffs = _diff_row(row, new_vals, team, have, want)
    if row.race_number != p.race_number:
        diffs.append(f"number {row.race_number} -> {p.race_number}")
    for fld, v in new_vals.items():
        setattr(row, fld, v)
    row.team_id, row.race_number = team.id, p.race_number
    _sync_drivers(row, want)
    row.source_name, row.source_url, row.checked_at = source_name, p.source_url, now
    db.flush()
    db.expire(row, ["drivers"])  # positions changed in the database; drop the stale in-memory order
    if diffs:
        stats.updated += 1
        stats.changes.append(f"{label} #{p.race_number}: " + "; ".join(diffs))
    return row


def _apply_event(db: DbSession, cache: Resolver, series: Series, event: Event, season: Season, incoming: list[ParsedEntry],
                 source_name: str, now: datetime, stats: EntryStats) -> None:
    owned = list(db.scalars(
        select(VehicleEntry).where(VehicleEntry.event_id == event.id, VehicleEntry.source_name.is_not(None))
    ))
    if is_fixture(source_name) and any(not is_fixture(e.source_name or "") for e in owned):
        stats.warnings.append(f"event {event.slug}: kept {len(owned)} entries from a live source; fixture data ignored")
        return
    if owned and len(incoming) < EVENT_SHRINK_RATIO * len(owned):
        stats.warnings.append(
            f"event {event.slug}: source lists {len(incoming)} of {len(owned)} stored entries; left unchanged"
        )
        return

    by_number = {e.race_number: e for e in owned}
    wanted = {p.race_number for p in incoming}
    for p in incoming:
        _upsert(db, cache, series, by_number.get(p.race_number), p, season=season, event=event,
                source_name=source_name, now=now, stats=stats, label=event.slug)

    for number, row in by_number.items():
        if number not in wanted:
            db.delete(row)
            stats.removed += 1
            stats.changes.append(f"{event.slug} #{number}: removed")
    db.flush()
    stats.events_applied += 1


def _apply_season(db: DbSession, cache: Resolver, series: Series, season: Season, incoming: list[ParsedEntry],
                  source_name: str, now: datetime, stats: EntryStats) -> None:
    """Season-wide roster (event_id NULL)."""
    teams = {}
    for p in incoming:  # resolve teams first: scope = the season rows of the teams this list names
        teams[p.team_external_id or p.team_name] = cache.team(p.team_name, p.team_external_id, p.team_aliases)
    team_ids = {t.id for t in teams.values()}
    rows = list(db.scalars(select(VehicleEntry).where(
        VehicleEntry.season_id == season.id, VehicleEntry.event_id.is_(None), VehicleEntry.team_id.in_(team_ids))))
    live = [e for e in rows if e.source_name is not None]
    if is_fixture(source_name) and any(not is_fixture(e.source_name or "") for e in live):
        stats.warnings.append(f"season {season.year}: kept {len(live)} roster entries from a live source; fixture data ignored")
        return
    if live and len(incoming) < EVENT_SHRINK_RATIO * len(live):
        stats.warnings.append(f"season {season.year}: source lists {len(incoming)} of {len(live)} stored roster entries; left unchanged")
        return

    by_number = {(e.team_id, e.race_number): e for e in rows if e.race_number is not None}
    by_driver = {lk.driver.slug: e for e in rows for lk in e.drivers}
    kept: set = set()
    for p in incoming:
        team = teams[p.team_external_id or p.team_name]
        row = by_number.get((team.id, p.race_number)) if p.race_number is not None else None
        if row is None and p.drivers:
            # a renumbered car, or a number not published yet: a single-driver entry is identified by its driver
            row = by_driver.get(p.drivers[0].slug) if len(p.drivers) == 1 else None
        if row is not None and row.id in kept:
            row = None
        out = _upsert(db, cache, series, row, p, season=season, event=None, source_name=source_name, now=now,
                      stats=stats, label=f"{season.year} {team.slug}")
        kept.add(out.id)
    for e in rows:
        if e.id not in kept:
            stats.removed += 1
            stats.changes.append(f"{season.year} {e.team.slug} #{e.race_number}: removed")
            db.delete(e)
    db.flush()
    stats.events_applied += 1


def apply_parsed_entries(
    db: DbSession, series: Series, parsed: list[ParsedEntry], *, source_name: str, now: datetime | None = None,
    source_id: str | None = None,
) -> EntryStats:
    now = now or datetime.now(UTC)
    stats = EntryStats(seen=len(parsed))
    cache = Resolver(db, series, source_id, now)

    groups: dict[tuple[int, str | None], list[ParsedEntry]] = {}
    for p in parsed:
        groups.setdefault((p.season_year, p.event_external_id), []).append(p)

    for (year, event_key), incoming in groups.items():
        numbers = [p.race_number for p in incoming if p.race_number is not None]
        label = event_key or f"season {year}"
        if len(numbers) != len(set(numbers)):
            stats.warnings.append(f"{label}: duplicate race numbers in source; skipped")
            continue
        season = db.scalar(select(Season).where(Season.series_id == series.id, Season.year == year))
        event = None
        if event_key is not None:
            event = db.scalar(select(Event).where(Event.season_id == season.id, Event.external_id == event_key)) if season else None
            if event is None:
                stats.warnings.append(f"event {event_key}: not in the schedule yet; entries skipped")
                continue
        elif season is None:
            stats.warnings.append(f"season {year}: not in the schedule yet; roster skipped")
            continue
        before = (stats.inserted, stats.updated, stats.removed, stats.events_applied, len(stats.changes))
        try:
            with db.begin_nested():
                if event is None:
                    _apply_season(db, cache, series, season, incoming, source_name, now, stats)
                else:
                    _apply_event(db, cache, series, event, season, incoming, source_name, now, stats)
        except Exception as exc:  # noqa: BLE001 - one event must never take the others down
            log.exception("entry apply failed", extra={"event": label})
            stats.inserted, stats.updated, stats.removed, stats.events_applied = before[:4]
            del stats.changes[before[4]:]
            stats.warnings.append(f"{label}: {type(exc).__name__}: {exc}; left unchanged")
            cache.clear()
    db.flush()
    return stats


__all__ = ["EntryStats", "apply_parsed_entries"]
