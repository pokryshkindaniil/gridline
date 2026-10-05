"""gridline identity-report — canonical entities, their aliases, and likely duplicates that are still separate.

    gridline identity-report [--limit N]

Read-only. It never merges anything: the likely-duplicate lists are suggestions for a human, who may add a curated
alias to `gridline_shared/aliases.py` (the only way two spellings become one entity).

A pair is a *likely duplicate* when their names are very similar (difflib ratio >= 0.85) or the surnames are equal
and one first name is a prefix of the other ('Jon' / 'Jonathan'). Two drivers who ever share a car are by definition
different people and are never suggested. 'Same surname, different first name' pairs are listed separately as
information: they are usually relatives (Charles / Arthur Leclerc), not duplicates.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from itertools import combinations

from gridline_shared import normalize_name
from sqlalchemy import select
from sqlalchemy.orm import Session as Db

from .db import SessionLocal
from .models import (
    Driver,
    DriverAlias,
    Manufacturer,
    ManufacturerAlias,
    Series,
    Team,
    TeamAlias,
    VehicleEntryDriver,
)

SIMILAR = 0.85


@dataclass
class Suggestion:
    a: str
    b: str
    sources_a: list[str]
    sources_b: list[str]
    ratio: float


@dataclass
class Report:
    drivers: int = 0
    driver_aliases: int = 0  # every recorded spelling
    driver_variants: list[tuple[str, str, str]] = field(default_factory=list)  # (canonical, spelling, source) that differ
    driver_likely: list[Suggestion] = field(default_factory=list)
    driver_same_surname: list[Suggestion] = field(default_factory=list)
    teams: dict[str, int] = field(default_factory=dict)  # series short name -> teams
    team_aliases: int = 0
    team_variants: list[tuple[str, str, str, str]] = field(default_factory=list)  # (series, canonical, spelling, source)
    team_likely: list[tuple[str, Suggestion]] = field(default_factory=list)
    team_cross_series: list[tuple[str, list[str]]] = field(default_factory=list)
    manufacturers: int = 0
    manufacturer_aliases: int = 0
    manufacturer_variants: list[tuple[str, str, str]] = field(default_factory=list)
    manufacturer_likely: list[Suggestion] = field(default_factory=list)


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_name(a), normalize_name(b)).ratio()


def _prefix_related(a: Driver, b: Driver) -> bool:
    fa, fb = normalize_name(a.first_name), normalize_name(b.first_name)
    short, long = sorted((fa, fb), key=len)
    return len(short) >= 3 and long.startswith(short)


def build_report(db: Db) -> Report:
    r = Report()
    series = {s.id: s for s in db.scalars(select(Series))}

    # ------------------------------------------------------------ drivers
    drivers = list(db.scalars(select(Driver).order_by(Driver.last_name, Driver.first_name)))
    sources: dict = defaultdict(set)
    for a in db.scalars(select(DriverAlias)):
        r.driver_aliases += 1
        sources[a.driver_id].add(a.source_name)
        drv = next((d for d in drivers if d.id == a.driver_id), None)
        if drv and normalize_name(a.source_value) != normalize_name(drv.canonical_name):
            r.driver_variants.append((drv.canonical_name, a.source_value, a.source_name))
    r.drivers = len(drivers)
    crews: dict = defaultdict(set)
    for entry_id, driver_id in db.execute(select(VehicleEntryDriver.vehicle_entry_id, VehicleEntryDriver.driver_id)):
        crews[entry_id].add(driver_id)
    together = {frozenset(p) for crew in crews.values() for p in combinations(crew, 2)}
    for a, b in combinations(drivers, 2):
        if frozenset((a.id, b.id)) in together:
            continue
        s = Suggestion(a.canonical_name, b.canonical_name, sorted(sources[a.id]), sorted(sources[b.id]),
                       _ratio(a.canonical_name, b.canonical_name))
        same_last = normalize_name(a.last_name) == normalize_name(b.last_name)
        if s.ratio >= SIMILAR or (same_last and _prefix_related(a, b)):
            r.driver_likely.append(s)
        elif same_last:
            r.driver_same_surname.append(s)
    r.driver_likely.sort(key=lambda s: -s.ratio)

    # ------------------------------------------------------------ teams
    teams = list(db.scalars(select(Team).order_by(Team.name)))
    by_series: dict = defaultdict(list)
    for t in teams:
        by_series[t.series_id].append(t)
        label = series[t.series_id].short_name
        r.teams[label] = r.teams.get(label, 0) + 1
    tsources: dict = defaultdict(set)
    for a in db.scalars(select(TeamAlias)):
        r.team_aliases += 1
        tsources[a.team_id].add(a.source_name)
        t = next((x for x in teams if x.id == a.team_id), None)
        if t and normalize_name(a.source_value) != normalize_name(t.name):
            r.team_variants.append((series[t.series_id].short_name, t.name, a.source_value, a.source_name))
    for sid, rows in by_series.items():
        for a, b in combinations(rows, 2):
            ratio = _ratio(a.name, b.name)
            if ratio >= SIMILAR:
                r.team_likely.append((series[sid].short_name, Suggestion(
                    a.name, b.name, sorted(tsources[a.id]), sorted(tsources[b.id]), ratio)))
    names: dict = defaultdict(set)
    for t in teams:
        names[t.slug].add(series[t.series_id].short_name)
    r.team_cross_series = sorted((slug, sorted(v)) for slug, v in names.items() if len(v) > 1)

    # ------------------------------------------------------------ manufacturers
    makes = list(db.scalars(select(Manufacturer).order_by(Manufacturer.canonical_name)))
    r.manufacturers = len(makes)
    msources: dict = defaultdict(set)
    for a in db.scalars(select(ManufacturerAlias)):
        r.manufacturer_aliases += 1
        msources[a.manufacturer_id].add(a.source_name)
        m = next((x for x in makes if x.id == a.manufacturer_id), None)
        if m and normalize_name(a.source_value) != normalize_name(m.canonical_name):
            r.manufacturer_variants.append((m.canonical_name, a.source_value, a.source_name))
    for a, b in combinations(makes, 2):
        ratio = _ratio(a.canonical_name, b.canonical_name)
        if ratio >= 0.75 or normalize_name(a.canonical_name).startswith(normalize_name(b.canonical_name)) \
                or normalize_name(b.canonical_name).startswith(normalize_name(a.canonical_name)):
            r.manufacturer_likely.append(Suggestion(a.canonical_name, b.canonical_name, sorted(msources[a.id]),
                                                    sorted(msources[b.id]), ratio))
    return r


def _src(names: list[str]) -> str:
    return " / ".join(names) or "-"


def format_report(r: Report, limit: int = 40) -> str:
    L = ["Drivers:", f"  {r.drivers} canonical drivers, {r.driver_aliases} recorded source spellings "
         f"({len(r.driver_variants)} differ from the canonical name)"]
    if r.driver_variants:
        L.append("  Aliases (spelling differs from canonical):")
        L += [f"    {canon}  <-  {spell!r}  [{src}]" for canon, spell, src in sorted(r.driver_variants)]
    L.append("  Potential driver duplicates (NOT merged; add a curated alias to confirm):")
    L += [f"    {s.a}\n    {s.b}\n    sources: {_src(s.sources_a)} / {_src(s.sources_b)}   similarity {s.ratio:.2f}\n"
          for s in r.driver_likely[:limit]] or ["    none"]
    L.append(f"  Same surname, different first name (information, usually different people): {len(r.driver_same_surname)}")
    L += [f"    {s.a}  |  {s.b}" for s in r.driver_same_surname[:limit]]
    L += ["", "Teams (identity is per series):",
          "  " + ", ".join(f"{k}: {v}" for k, v in sorted(r.teams.items())) + f"   ({r.team_aliases} recorded source spellings)"]
    if r.team_variants:
        L.append("  Aliases (spelling differs from canonical):")
        L += [f"    [{s}] {c}  <-  {v!r}  [{src}]" for s, c, v, src in sorted(r.team_variants)]
    L.append("  Unresolved: very similar team names in one series (NOT merged):")
    L += [f"    [{s}] {x.a}  |  {x.b}   similarity {x.ratio:.2f}" for s, x in r.team_likely[:limit]] or ["    none"]
    L.append("  Same team name in several series (separate rows; cross-series organisation identity is not modelled yet):")
    L += [f"    {slug}: {', '.join(v)}" for slug, v in r.team_cross_series[:limit]] or ["    none"]
    L += ["", "Manufacturers:", f"  {r.manufacturers} canonical manufacturers, {r.manufacturer_aliases} recorded source spellings"]
    if r.manufacturer_variants:
        L += [f"    {c}  <-  {v!r}  [{src}]" for c, v, src in sorted(r.manufacturer_variants)]
    L.append("  Potentially related names (NOT merged):")
    L += [f"    {s.a}  |  {s.b}" for s in r.manufacturer_likely] or ["    none"]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="gridline identity-report")
    ap.add_argument("--limit", type=int, default=40)
    args = ap.parse_args(argv)
    with SessionLocal() as db:
        print(format_report(build_report(db), args.limit))
    return 0
