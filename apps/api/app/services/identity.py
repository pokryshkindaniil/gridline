"""Resolve source names to canonical drivers, teams, and vehicles."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from gridline_shared import normalize_name, slugify
from gridline_shared.aliases import DRIVER_ALIASES, MANUFACTURER_ALIASES, TEAM_ALIASES, DriverAlias, NameAlias
from gridline_sources import ParsedDriver, all_sources
from sqlalchemy import select
from sqlalchemy.orm import Session as Db

from ..models import (
    Driver,
    Manufacturer,
    ManufacturerAlias,
    Series,
    Team,
    TeamAlias,
    VehicleEntry,
    VehicleEntryDriver,
    VehicleModel,
)
from ..models import (
    DriverAlias as DriverAliasRow,
)

log = logging.getLogger(__name__)


def default_source_id(series_slug: str) -> str:
    return next((s.source_id for s in all_sources() if s.series_slug == series_slug), series_slug)


def vehicle_category(series: Series, class_name: str | None) -> str | None:
    """Return a car category only when the series makes it unambiguous."""
    if series.category == "formula":
        return "Formula 1" if series.slug == "formula-1" else None
    if series.slug == "fia-wec":
        return class_name
    if series.slug == "gt-world-challenge-europe":
        return "GT3"
    return None


class Resolver:
    """Per-run cache + resolution for one source/series. Flushes but never commits."""

    def __init__(self, db: Db, series: Series, source_id: str | None = None, now: datetime | None = None) -> None:
        self.db, self.series = db, series
        self.source = source_id or default_source_id(series.slug)
        self.now = now or datetime.now(UTC)
        self._drivers: dict[str, Driver] = {}
        self._teams: dict[str, Team] = {}
        self._makes: dict[str, Manufacturer] = {}
        self._models: dict[tuple, VehicleModel] = {}
        self._driver_curated = {normalize_name(a.variant): a for a in DRIVER_ALIASES if self.source in a.sources}
        self._team_curated = {normalize_name(a.variant): a for a in TEAM_ALIASES.get(series.slug, ()) if self.source in a.sources}
        self._make_curated = {normalize_name(a.variant): a for a in MANUFACTURER_ALIASES if self.source in a.sources}

    def clear(self) -> None:
        self._drivers.clear(); self._teams.clear(); self._makes.clear(); self._models.clear()  # noqa: E702

    def driver(self, d: ParsedDriver) -> Driver:
        spelling = f"{d.first_name} {d.last_name}"
        norm = normalize_name(spelling)
        key = f"{d.external_id}|{norm}" if d.external_id else norm
        row = self._drivers.get(key)
        if row is None:
            row = self._find_driver(d, norm) or self._create_driver(d, norm)
            self._drivers[key] = row
        self._note_driver_alias(row, spelling, norm, d.external_id)
        if row.nationality_code is None and d.nationality_code:
            row.nationality_code = d.nationality_code
        if row.birth_date is None and d.birth_date:
            row.birth_date = d.birth_date
        return row

    def _find_driver(self, d: ParsedDriver, norm: str) -> Driver | None:
        if d.external_id:
            hit = self.db.scalar(
                select(Driver).join(DriverAliasRow).where(
                    DriverAliasRow.source_name == self.source, DriverAliasRow.source_external_id == d.external_id))
            if hit:
                return hit
        hit = self.db.scalar(
            select(Driver).join(DriverAliasRow).where(
                DriverAliasRow.source_name == self.source, DriverAliasRow.normalized_value == norm))
        if hit:
            return hit
        cur = self._driver_curated.get(norm)
        if cur:
            return self._canonical_driver(cur)
        return self.db.scalar(select(Driver).where(Driver.slug == slugify(f"{d.first_name} {d.last_name}")))

    def _canonical_driver(self, cur: DriverAlias) -> Driver:
        slug = slugify(cur.canonical)
        row = self.db.scalar(select(Driver).where(Driver.slug == slug))
        if row is None:
            row = Driver(slug=slug, first_name=cur.first_name, last_name=cur.last_name)
            self.db.add(row)
            self.db.flush()
        return row

    def _create_driver(self, d: ParsedDriver, norm: str) -> Driver:
        row = Driver(slug=slugify(f"{d.first_name} {d.last_name}"), first_name=d.first_name, last_name=d.last_name,
                     nationality_code=d.nationality_code, birth_date=d.birth_date)
        self.db.add(row)
        self.db.flush()
        return row

    def _note_driver_alias(self, row: Driver, spelling: str, norm: str, external_id: str | None) -> None:
        alias = self.db.scalar(select(DriverAliasRow).where(
            DriverAliasRow.source_name == self.source, DriverAliasRow.normalized_value == norm))
        if alias is None:
            self.db.add(DriverAliasRow(driver_id=row.id, source_name=self.source, source_value=spelling,
                                       normalized_value=norm, source_external_id=external_id, first_seen_at=self.now))
            self.db.flush()
        elif external_id and alias.source_external_id is None:
            alias.source_external_id = external_id

    def team(self, name: str, external_id: str | None = None, extra_names: tuple[str, ...] = ()) -> Team:
        norm = normalize_name(name)
        key = f"{external_id}|{norm}" if external_id else norm
        row = self._teams.get(key)
        if row is None:
            row = self._find_team(name, norm, external_id) or self._create_team(name)
            self._teams[key] = row
        for i, spelling in enumerate((name, *extra_names)):
            self._note_team_alias(row, spelling, normalize_name(spelling), external_id if i == 0 else None)
        return row

    def _find_team(self, name: str, norm: str, external_id: str | None) -> Team | None:
        base = select(Team).join(TeamAlias).where(Team.series_id == self.series.id, TeamAlias.source_name == self.source)
        if external_id:
            hit = self.db.scalar(base.where(TeamAlias.source_external_id == external_id))
            if hit:
                return hit
        hit = self.db.scalar(base.where(TeamAlias.normalized_value == norm))
        if hit:
            return hit
        cur = self._team_curated.get(norm)
        if cur:
            return self._canonical_team(cur)
        return self.db.scalar(select(Team).where(Team.series_id == self.series.id, Team.slug == slugify(name)))

    def _canonical_team(self, cur: NameAlias) -> Team:
        slug = slugify(cur.canonical)
        row = self.db.scalar(select(Team).where(Team.series_id == self.series.id, Team.slug == slug))
        if row is None:
            row = Team(series_id=self.series.id, slug=slug, name=cur.canonical)
            self.db.add(row)
            self.db.flush()
        return row

    def _create_team(self, name: str) -> Team:
        row = Team(series_id=self.series.id, slug=slugify(name), name=name)
        self.db.add(row)
        self.db.flush()
        return row

    def _note_team_alias(self, row: Team, spelling: str, norm: str, external_id: str | None) -> None:
        alias = self.db.scalar(select(TeamAlias).where(TeamAlias.source_name == self.source, TeamAlias.normalized_value == norm))
        if alias is None:
            self.db.add(TeamAlias(team_id=row.id, source_name=self.source, source_value=spelling, normalized_value=norm,
                                  source_external_id=external_id, first_seen_at=self.now))
            self.db.flush()
        elif external_id and alias.source_external_id is None:
            alias.source_external_id = external_id

    def manufacturer(self, name: str | None) -> Manufacturer | None:
        if not name or not name.strip():
            return None
        norm = normalize_name(name)
        row = self._makes.get(norm)
        if row is None:
            row = self.db.scalar(select(Manufacturer).join(ManufacturerAlias).where(
                ManufacturerAlias.source_name == self.source, ManufacturerAlias.normalized_value == norm))
            if row is None and (cur := self._make_curated.get(norm)):
                row = self._canonical_manufacturer(cur.canonical)
            if row is None:
                row = self.db.scalar(select(Manufacturer).where(Manufacturer.slug == slugify(name)))
            if row is None:
                row = Manufacturer(slug=slugify(name), canonical_name=name.strip())
                self.db.add(row)
                self.db.flush()
            self._makes[norm] = row
        if self.db.scalar(select(ManufacturerAlias.id).where(
                ManufacturerAlias.source_name == self.source, ManufacturerAlias.normalized_value == norm)) is None:
            self.db.add(ManufacturerAlias(manufacturer_id=row.id, source_name=self.source, source_value=name.strip(),
                                          normalized_value=norm, first_seen_at=self.now))
            self.db.flush()
        return row

    def _canonical_manufacturer(self, canonical: str) -> Manufacturer:
        row = self.db.scalar(select(Manufacturer).where(Manufacturer.slug == slugify(canonical)))
        if row is None:
            row = Manufacturer(slug=slugify(canonical), canonical_name=canonical)
            self.db.add(row)
            self.db.flush()
        return row

    def vehicle_model(self, make: Manufacturer | None, name: str | None, *, class_name: str | None = None,
                      source_name: str | None = None, source_url: str | None = None) -> VehicleModel | None:
        """Model identity is (manufacturer, slug of the model name): 'GR010 - Hybrid' and 'GR010 Hybrid' are one
        model, '911 GT3 R EVO' and '911 GT3 R (992) EVO' stay two (no guessing which is which)."""
        if make is None or not name or not name.strip():
            return None
        slug = slugify(name)
        key = (make.id, slug)
        row = self._models.get(key)
        if row is None:
            row = self.db.scalar(select(VehicleModel).where(VehicleModel.manufacturer_id == make.id, VehicleModel.slug == slug))
            if row is None:
                row = VehicleModel(
                    manufacturer_id=make.id, slug=slug, canonical_name=name.strip(),
                    season_year=None, category=vehicle_category(self.series, class_name),
                    source_name=source_name, source_url=source_url, checked_at=self.now)
                self.db.add(row)
                self.db.flush()
            self._models[key] = row
        if source_name and row.source_name != source_name:
            row.source_name, row.source_url, row.checked_at = source_name, source_url, self.now
        return row


@dataclass
class IdentityChanges:
    merged_drivers: list[str] = field(default_factory=list)
    merged_teams: list[str] = field(default_factory=list)
    aliases_added: int = 0
    entries_linked: int = 0


def merge_drivers(db: Db, keep: Driver, drop: Driver) -> None:
    """Re-point everything of `drop` to `keep`, then delete `drop`. Entry crews never end up with a driver twice."""
    keep_entries = {lk.vehicle_entry_id for lk in db.scalars(select(VehicleEntryDriver).where(VehicleEntryDriver.driver_id == keep.id))}
    for link in list(db.scalars(select(VehicleEntryDriver).where(VehicleEntryDriver.driver_id == drop.id))):
        if link.vehicle_entry_id in keep_entries:
            db.delete(link)
        else:
            link.driver_id = keep.id
    db.flush()
    for alias in list(db.scalars(select(DriverAliasRow).where(DriverAliasRow.driver_id == drop.id))):
        clash = db.scalar(select(DriverAliasRow).where(
            DriverAliasRow.source_name == alias.source_name, DriverAliasRow.normalized_value == alias.normalized_value,
            DriverAliasRow.driver_id == keep.id))
        if clash:
            db.delete(alias)
        else:
            alias.driver_id = keep.id
    db.flush()
    keep.nationality_code = keep.nationality_code or drop.nationality_code
    keep.birth_date = keep.birth_date or drop.birth_date
    db.expire(drop, ["aliases"])
    db.delete(drop)
    db.flush()


def merge_teams(db: Db, keep: Team, drop: Team) -> None:
    keep_keys = {(e.season_id, e.event_id, e.race_number) for e in db.scalars(select(VehicleEntry).where(VehicleEntry.team_id == keep.id))}
    for e in list(db.scalars(select(VehicleEntry).where(VehicleEntry.team_id == drop.id))):
        if (e.season_id, e.event_id, e.race_number) in keep_keys:
            db.delete(e)
        else:
            e.team_id = keep.id
    db.flush()
    for alias in list(db.scalars(select(TeamAlias).where(TeamAlias.team_id == drop.id))):
        clash = db.scalar(select(TeamAlias).where(TeamAlias.source_name == alias.source_name,
                                                  TeamAlias.normalized_value == alias.normalized_value,
                                                  TeamAlias.team_id == keep.id))
        if clash:
            db.delete(alias)
        else:
            alias.team_id = keep.id
    db.flush()
    db.expire(drop, ["aliases"])
    db.delete(drop)
    db.flush()


def apply_curated(db: Db, now: datetime | None = None) -> IdentityChanges:
    """Make the stored entities agree with gridline_shared.aliases (idempotent). Spellings that are NOT listed
    there are left exactly as they are."""
    now = now or datetime.now(UTC)
    out = IdentityChanges()
    for cur in DRIVER_ALIASES:
        canon = db.scalar(select(Driver).where(Driver.slug == slugify(cur.canonical)))
        var = db.scalar(select(Driver).where(Driver.slug == slugify(cur.variant)))
        if var is not None and var is not canon:
            if canon is None:
                var.slug, var.first_name, var.last_name = slugify(cur.canonical), cur.first_name, cur.last_name
                db.flush()
                canon = var
            else:
                merge_drivers(db, canon, var)
                out.merged_drivers.append(f"{cur.variant} -> {cur.canonical}")
        if canon is None:
            continue
        for source in cur.sources:
            norm = normalize_name(cur.variant)
            alias = db.scalar(select(DriverAliasRow).where(DriverAliasRow.source_name == source, DriverAliasRow.normalized_value == norm))
            if alias is None:
                db.add(DriverAliasRow(driver_id=canon.id, source_name=source, source_value=cur.variant,
                                      normalized_value=norm, first_seen_at=now))
                out.aliases_added += 1
            elif alias.driver_id != canon.id:
                alias.driver_id = canon.id
    for series_slug, aliases in TEAM_ALIASES.items():
        series = db.scalar(select(Series).where(Series.slug == series_slug))
        if series is None:
            continue
        for cur in aliases:
            canon = db.scalar(select(Team).where(Team.series_id == series.id, Team.slug == slugify(cur.canonical)))
            var = db.scalar(select(Team).where(Team.series_id == series.id, Team.slug == slugify(cur.variant)))
            if var is not None and var is not canon:
                if canon is None:
                    var.slug, var.name = slugify(cur.canonical), cur.canonical
                    db.flush()
                    canon = var
                else:
                    merge_teams(db, canon, var)
                    out.merged_teams.append(f"{series_slug}: {cur.variant} -> {cur.canonical}")
            if canon is None:
                continue
            for source in cur.sources:
                norm = normalize_name(cur.variant)
                alias = db.scalar(select(TeamAlias).where(TeamAlias.source_name == source, TeamAlias.normalized_value == norm))
                if alias is None:
                    db.add(TeamAlias(team_id=canon.id, source_name=source, source_value=cur.variant, normalized_value=norm,
                                     first_seen_at=now))
                    out.aliases_added += 1
                elif alias.team_id != canon.id:
                    alias.team_id = canon.id
    db.flush()
    return out


def backfill(db: Db, now: datetime | None = None) -> IdentityChanges:
    """Create the canonical rows/aliases for data imported before identity existed (idempotent).

    Drivers and teams get an alias with the spelling stored today, under the source of every series they appear in;
    entries get their Manufacturer / VehicleModel links."""
    now = now or datetime.now(UTC)
    out = IdentityChanges()
    series_by_id = {s.id: s for s in db.scalars(select(Series))}
    team_series = {t.id: series_by_id[t.series_id] for t in db.scalars(select(Team))}

    rows = db.execute(
        select(Driver, Team.series_id).join(VehicleEntryDriver, VehicleEntryDriver.driver_id == Driver.id)
        .join(VehicleEntry, VehicleEntry.id == VehicleEntryDriver.vehicle_entry_id)
        .join(Team, Team.id == VehicleEntry.team_id).distinct()
    )
    for drv, series_id in rows:
        source = default_source_id(series_by_id[series_id].slug)
        spelling = f"{drv.first_name} {drv.last_name}"
        norm = normalize_name(spelling)
        if db.scalar(select(DriverAliasRow.id).where(DriverAliasRow.source_name == source, DriverAliasRow.normalized_value == norm)) is None:
            db.add(DriverAliasRow(driver_id=drv.id, source_name=source, source_value=spelling, normalized_value=norm, first_seen_at=now))
            out.aliases_added += 1
            db.flush()

    for team in db.scalars(select(Team)):
        source = default_source_id(team_series[team.id].slug)
        norm = normalize_name(team.name)
        if db.scalar(select(TeamAlias.id).where(TeamAlias.source_name == source, TeamAlias.normalized_value == norm)) is None:
            db.add(TeamAlias(team_id=team.id, source_name=source, source_value=team.name, normalized_value=norm, first_seen_at=now))
            out.aliases_added += 1
            db.flush()

    pending = db.scalars(select(VehicleEntry).where(VehicleEntry.manufacturer.is_not(None), VehicleEntry.manufacturer_id.is_(None)))
    resolvers: dict = {}
    for e in pending:
        series = team_series[e.team_id]
        r = resolvers.get(series.id) or resolvers.setdefault(series.id, Resolver(db, series, now=now))
        make = r.manufacturer(e.manufacturer)
        e.manufacturer_id = make.id if make else None
        model = r.vehicle_model(make, e.model, class_name=e.class_name, source_name=e.source_name, source_url=e.source_url)
        e.vehicle_model_id = model.id if model else None
        out.entries_linked += 1
    db.flush()
    return out


def ensure_identity(db: Db) -> IdentityChanges:
    """Curated merges + backfill. Safe to run at any time, any number of times."""
    changes = apply_curated(db)
    b = backfill(db)
    changes.aliases_added += b.aliases_added
    changes.entries_linked += b.entries_linked
    return changes
