"""Development seed.  python -m app.seed

1. Upserts the series catalogue.
2. Runs every adapter in *fixture* mode through the real sync engine: schedules (F1 + GTWC fixtures are
   captured real data; WEC schedule + IMSA are SYNTHETIC) and, for GTWC and WEC, the entry lists
   (captured official pages, labelled "fixture snapshot"; a fixture never overwrites live entries).
3. Inserts a sample team / vehicle / driver roster for IMSA, the only series without an entry-list source.

!! The roster below is DEVELOPMENT SEED DATA. It is illustrative, unverified and must not be
!! presented as production data. Images are intentionally null (the UI falls back gracefully).
!! F1, GTWC and WEC rosters are NOT seeded here: step 2 loads captured official pages for them (labelled
!! "fixture snapshot"), and in a real run they come from `gridline sync`.
"""

from __future__ import annotations

import asyncio
import sys

from gridline_shared import slugify
from sqlalchemy import select
from sqlalchemy.orm import Session as Db

from .catalog import ensure_series
from .config import get_settings
from .db import SessionLocal
from .models import Driver, Season, Team, VehicleEntry, VehicleEntryDriver
from .sources.sync import run_sync

YEAR = 2026
D = tuple[str, str, str]  # first, last, nationality (ISO alpha-2)

# series slug -> teams. entry = (race number, [drivers]); vehicle = (manufacturer, model, class, number|None)
ROSTER: dict[str, list[dict]] = {
    "imsa-weathertech": [
        dict(name="Cadillac Whelen", vehicles=[("Cadillac", "V-Series.R", "GTP", "31")],
             entries=[("31", [("Jack", "Aitken", "GB"), ("Earl", "Bamber", "NZ"), ("Frederik", "Vesti", "DK"), ("Pipo", "Derani", "BR")])]),
        dict(name="Porsche Penske Motorsport (IMSA)", vehicles=[("Porsche", "963", "GTP", "7")],
             entries=[("7", [("Felipe", "Nasr", "BR"), ("Nick", "Tandy", "GB"), ("Laurin", "Heinrich", "DE")])]),
    ],
}


def _driver(db: Db, d: D) -> Driver:
    slug = slugify(f"{d[0]} {d[1]}")
    row = db.scalar(select(Driver).where(Driver.slug == slug))
    if row is None:
        row = Driver(slug=slug, first_name=d[0], last_name=d[1], nationality_code=d[2])
        db.add(row)
        db.flush()
    return row


def seed_roster(db: Db) -> None:
    series = ensure_series(db)
    for slug, teams in ROSTER.items():
        season = db.scalar(select(Season).where(Season.series_id == series[slug].id, Season.year == YEAR))
        if season is None:
            season = Season(series_id=series[slug].id, year=YEAR)
            db.add(season)
            db.flush()
        for t in teams:
            tslug = slugify(t["name"])
            team = db.scalar(select(Team).where(Team.series_id == series[slug].id, Team.slug == tslug))
            if team is None:
                team = Team(series_id=series[slug].id, slug=tslug, name=t["name"])
                db.add(team)
                db.flush()
            models = {num: (man, model, cls) for man, model, cls, num in t["vehicles"]}
            default = t["vehicles"][0]
            for num, drivers in t["entries"]:
                man, model, cls = models.get(num, default[:3])
                entry = db.scalar(select(VehicleEntry).where(
                    VehicleEntry.team_id == team.id, VehicleEntry.season_id == season.id,
                    VehicleEntry.event_id.is_(None), VehicleEntry.race_number == num))
                if entry is None:
                    entry = VehicleEntry(team_id=team.id, season_id=season.id, race_number=num,
                                         manufacturer=man, model=model, class_name=cls)
                    db.add(entry)
                    db.flush()
                have = {d.driver_id for d in entry.drivers}
                for pos, d in enumerate(drivers):
                    drv = _driver(db, d)
                    if drv.id not in have:
                        db.add(VehicleEntryDriver(vehicle_entry_id=entry.id, driver_id=drv.id, position=pos, role="driver"))
    db.commit()


def main() -> int:
    if get_settings().environment == "production":
        print("refusing to seed dev data with ENVIRONMENT=production", file=sys.stderr)
        return 2
    results = asyncio.run(run_sync(None, fixtures=True))
    for r in results:
        print(r.status.upper(), r.source_id, r.stats or r.error)
    with SessionLocal() as db:
        seed_roster(db)
    print("Seeded roster (DEV DATA, unverified).")
    return 1 if any(r.status == "failed" for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
