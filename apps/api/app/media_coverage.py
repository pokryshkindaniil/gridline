"""Compare the teams in the database with the logo registry (`apps/web/lib/media-manifest.json`).

    gridline media-coverage [--manifest PATH] [--fail-under PCT]

For every public series: how many teams exist, how many have their OWN logo in the registry (the key metric:
ACTUAL TEAM LOGO COVERAGE), how many would show a manufacturer logo instead, and which would fall back to the
typeset name. Registry lookups use exactly the UI's rules (team slug, restricted to the series the logo is for;
manufacturer slug + aliases; a manufacturer stands in only when the team runs one make). A series that is not
public (IMSA) is not reported: it is not part of the product.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from gridline_shared.identity import slugify
from sqlalchemy import select

from .db import SessionLocal
from .models import Series, Team, VehicleEntry
from .services.series_visibility import public_only

DEFAULT_MANIFEST = Path(__file__).resolve().parents[3] / "apps/web/lib/media-manifest.json"


@dataclass
class TeamRow:
    series: str            # short name, for display
    slug: str
    series_slug: str
    name: str
    manufacturers: frozenset[str]      # distinct vehicle manufacturers seen on the team's entries
    live: bool                         # at least one entry carries official-source provenance


@dataclass
class SeriesReport:
    name: str
    live: bool
    teams: int = 0
    team_logos: int = 0
    manufacturer_fallback: list[str] = field(default_factory=list)
    text_fallback: list[str] = field(default_factory=list)
    manufacturers: set[str] = field(default_factory=set)
    manufacturers_missing: set[str] = field(default_factory=set)

    @property
    def coverage(self) -> float:
        return 100.0 * self.team_logos / self.teams if self.teams else 100.0

    @property
    def identity_coverage(self) -> float:
        return 100.0 * (self.team_logos + len(self.manufacturer_fallback)) / self.teams if self.teams else 100.0


def load_registry(path: Path) -> dict:
    return json.loads(path.read_text())


def _manufacturer_index(registry: dict) -> dict[str, str]:
    idx: dict[str, str] = {}
    for slug, e in registry["manufacturers"].items():
        if e.get("logo"):
            idx[slug] = slug
            idx.update({a: slug for a in e.get("aliases", [])})
    return idx


def compute(rows: list[TeamRow], registry: dict) -> dict[str, SeriesReport]:
    teams = {s: e for s, e in registry["teams"].items() if e.get("logo")}
    makes = _manufacturer_index(registry)
    out: dict[str, SeriesReport] = {}
    for r in sorted(rows, key=lambda r: (r.series, r.slug)):
        rep = out.setdefault(r.series, SeriesReport(r.series, live=False))
        rep.live = rep.live or r.live
        rep.teams += 1
        slugs = {slugify(m) for m in r.manufacturers}
        rep.manufacturers |= slugs
        rep.manufacturers_missing |= {s for s in slugs if s not in makes}
        own = teams.get(r.slug)
        if own and (not own.get("series") or r.series_slug in own["series"]):
            rep.team_logos += 1
        elif len(slugs) == 1 and next(iter(slugs)) in makes:
            rep.manufacturer_fallback.append(r.slug)
        else:
            rep.text_fallback.append(r.slug)
    return out


def missing_files(registry: dict, public: Path) -> list[str]:
    srcs = [e["logo"]["src"] for k in ("teams", "manufacturers") for e in registry[k].values() if e.get("logo")]
    for e in registry.get("series", {}).values():  # curated series visuals: hero photograph and optional logo
        srcs += [a["src"] for a in (e.get("hero"), e.get("logo")) if a]
    return [s for s in srcs if not (public / s.lstrip("/")).is_file()]


def format_report(reports: dict[str, SeriesReport], registry: dict, orphans: list[str], broken: list[str]) -> str:
    L: list[str] = []
    tot_t = sum(r.teams for r in reports.values())
    tot_l = sum(r.team_logos for r in reports.values())
    for name, r in reports.items():
        L += [f"{name}:" + ("" if r.live else "   (dev seed / fixture data, not an official live import)"),
              f"  {r.teams} teams",
              f"  {r.team_logos} actual team logos",
              f"  {len(r.manufacturer_fallback)} manufacturer fallback",
              f"  {len(r.text_fallback)} text fallback",
              f"  ACTUAL TEAM LOGO COVERAGE: {r.coverage:.0f}%   (any logo, incl. manufacturer fallback: {r.identity_coverage:.0f}%)",
              f"  manufacturers: {len(r.manufacturers) - len(r.manufacturers_missing)}/{len(r.manufacturers)} have a logo", ""]
    L.append(f"TOTAL ACTUAL TEAM LOGO COVERAGE: {tot_l}/{tot_t} teams ({100.0 * tot_l / tot_t if tot_t else 100.0:.0f}%)")
    L += ["", "Missing actual team logos (slug → what the UI shows instead):"]
    any_missing = False
    for name, r in reports.items():
        for s in r.manufacturer_fallback:
            L.append(f"- {name}/{s}  → manufacturer logo")
            any_missing = True
        for s in r.text_fallback:
            L.append(f"- {name}/{s}  → team name as text")
            any_missing = True
    if not any_missing:
        L.append("- none")
    miss_m = sorted({m for r in reports.values() for m in r.manufacturers_missing})
    L += ["", "Missing manufacturer logos: " + (", ".join(miss_m) if miss_m else "none")]
    if orphans:
        L += ["", "Registry teams not present in the database (fine, e.g. series not imported yet): " + ", ".join(orphans)]
    if broken:
        L += ["", "BROKEN registry entries (file missing on disk): " + ", ".join(broken)]
    return "\n".join(L)


def gather(db_factory=SessionLocal) -> list[TeamRow]:
    with db_factory() as db:
        makes: dict = defaultdict(set)
        live: dict = defaultdict(bool)
        for team_id, make, src in db.execute(select(VehicleEntry.team_id, VehicleEntry.manufacturer, VehicleEntry.source_name)):
            if make:
                makes[team_id].add(make)
            live[team_id] = live[team_id] or src is not None
        return [TeamRow(s.short_name, t.slug, s.slug, t.name, frozenset(makes[t.id]), live[t.id])
                for t, s in db.execute(select(Team, Series).join(Series, Team.series_id == Series.id).where(public_only()))]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="gridline media-coverage")
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--fail-under", type=float, default=None, metavar="PCT", help="exit 1 if overall team-logo coverage is below PCT")
    args = ap.parse_args(argv)
    registry = load_registry(args.manifest)
    rows = gather()
    reports = compute(rows, registry)
    in_db = {r.slug for r in rows}
    orphans = sorted(set(registry["teams"]) - in_db)
    broken = missing_files(registry, args.manifest.parents[1] / "public")
    print(format_report(reports, registry, orphans, broken))
    teams = sum(r.teams for r in reports.values())
    pct = 100.0 * sum(r.team_logos for r in reports.values()) / teams if teams else 100.0
    return 1 if broken or (args.fail_under is not None and pct < args.fail_under) else 0
