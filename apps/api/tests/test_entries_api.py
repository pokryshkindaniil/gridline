"""Entry lists through the public API: per-event lineups, provenance, health. Data comes from the real fixtures
via the real sync path (fixture mode)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.models import Event, Season, Series, Team, VehicleEntry
from app.routers.teams import default_event, resolve_entries
from app.sources import sync as sync_mod

from .conftest import TestSession

GT = "gt-world-challenge-europe"


@pytest.fixture
async def synced(db, series):
    await sync_mod.run_sync(["gt_world_challenge", "fia_wec"], fixtures=True, db_factory=TestSession)
    return db


def event_id(db, series_slug, external_id):
    return str(db.scalar(select(Event.id).join(Season, Event.season_id == Season.id).join(Series, Season.series_id == Series.id)
                         .where(Series.slug == series_slug, Event.external_id == external_id)))


def team_by_slug(client, series, event, slug):
    teams = client.get(f"/series/{series}/teams", params={"event_id": event}).json()
    return next((t for t in teams if t["slug"] == slug), None)


async def test_entry_events_list_every_published_event_with_provenance(client, synced):
    rows = client.get(f"/series/{GT}/entry-events").json()
    assert [r["event"]["name"] for r in rows][:2] == ["Circuit Paul Ricard", "Brands Hatch"]
    assert len(rows) == 9
    assert sum(r["is_default"] for r in rows) == 1
    barcelona = next(r for r in rows if r["event"]["slug"] == "barcelona")
    assert barcelona["competition"] == "Sprint Cup" and barcelona["entry_count"] == 44
    assert barcelona["source_url"] == "https://www.gt-world-challenge-europe.com/entry-list/2026/barcelona"
    assert barcelona["source_name"].endswith("(entry list, fixture snapshot)") and barcelona["is_fixture"] is True
    assert barcelona["checked_at"]


async def test_sprint_cup_event_shows_two_driver_crews(client, synced, db):
    t = team_by_slug(client, GT, event_id(db, GT, "e254"), "boutsen-vds")
    two = next(e for e in t["entries"] if e["race_number"] == "2")
    assert [d["last_name"] for d in two["drivers"]] == ["Müller", "Boccolacci"]
    assert {len(e["drivers"]) for e in t["entries"]} == {2}
    assert two["vehicle"]["manufacturer"] == "Porsche" and two["vehicle"]["class_name"] == "Pro"


async def test_same_team_and_car_shows_a_different_lineup_per_event(client, synced, db):
    last_names = lambda ev: [d["last_name"] for d in next(  # noqa: E731
        e for e in team_by_slug(client, GT, event_id(db, GT, ev), "boutsen-vds")["entries"] if e["race_number"] == "2")["drivers"]]
    assert last_names("e254") == ["Müller", "Boccolacci"]      # Barcelona
    assert last_names("e247") == ["Boccolacci", "Schuring"]    # Brands Hatch
    assert last_names("e251") == ["Picariello", "Boccolacci"]  # Magny-Cours


async def test_endurance_cup_event_shows_three_driver_crews_and_spa_four(client, synced, db):
    paul_ricard = client.get(f"/series/{GT}/teams", params={"event_id": event_id(db, GT, "e246")}).json()
    assert max(len(e["drivers"]) for t in paul_ricard for e in t["entries"]) == 3
    spa = client.get(f"/series/{GT}/teams", params={"event_id": event_id(db, GT, "e249")}).json()
    assert {len(e["drivers"]) for t in spa for e in t["entries"]} == {3, 4}


async def test_team_detail_follows_the_requested_event(client, synced, db):
    detail = client.get("/teams/boutsen-vds", params={"event_id": event_id(db, GT, "e247")}).json()
    assert detail["event"]["slug"] == "brands-hatch"
    assert [d["last_name"] for d in next(e for e in detail["entries"] if e["race_number"] == "2")["drivers"]] == [
        "Boccolacci", "Schuring"]


async def test_wec_multi_car_team_with_three_drivers_each(client, synced, db):
    spa = event_id(db, "fia-wec", "totalenergies-6-hours-of-spa-francorchamps-2026")
    t = team_by_slug(client, "fia-wec", spa, "ferrari-af-corse")
    assert [e["race_number"] for e in t["entries"]] == ["50", "51"]
    assert [len(e["drivers"]) for e in t["entries"]] == [3, 3]
    assert {e["vehicle"]["class_name"] for e in t["entries"]} == {"Hypercar"}


async def test_wec_event_specific_replacement_driver(client, synced, db):
    def crew(slug):
        t = team_by_slug(client, "fia-wec", event_id(db, "fia-wec", slug), "cadillac-hertz-team-jota")
        return [d["last_name"] for d in next(e for e in t["entries"] if e["race_number"] == "12")["drivers"]]

    assert crew("official-prologue-imola-2026") == ["Lynn", "Stevens", "Nato"]
    assert crew("lone-star-le-mans-2026") == ["Stevens", "Nato", "Taylor"]


async def test_season_wide_seed_rows_do_not_leak_into_a_listed_event(client, synced, db):
    gt = db.scalar(select(Team).where(Team.slug == "boutsen-vds"))
    season = db.scalar(select(Season).where(Season.series_id == gt.series_id))
    db.add(VehicleEntry(team_id=gt.id, season_id=season.id, race_number="999", model="Seed"))
    db.commit()
    t = team_by_slug(client, GT, event_id(db, GT, "e254"), "boutsen-vds")
    assert "999" not in [e["race_number"] for e in t["entries"]]


async def test_default_event_is_the_next_unfinished_one_else_the_latest(synced, db):
    events = list(db.scalars(select(Event).join(Season).where(Event.external_id.in_(["e247", "e250", "e254"]))
                             .order_by(Event.start_date)))
    assert default_event(events, today=date(2026, 6, 1)).external_id == "e250"  # Misano is next
    assert default_event(events, today=date(2026, 10, 4)).external_id == "e254"  # Barcelona is the last day
    assert default_event(events, today=date(2027, 1, 1)).external_id == "e254"  # season over: latest
    assert default_event([], today=date(2026, 6, 1)) is None


async def test_unknown_or_foreign_event_is_404(client, synced, db):
    other = event_id(db, "fia-wec", "totalenergies-6-hours-of-spa-francorchamps-2026")
    assert client.get(f"/series/{GT}/teams", params={"event_id": other}).status_code == 404
    assert client.get(f"/series/{GT}/teams", params={"event_id": "00000000-0000-0000-0000-000000000000"}).status_code == 404


def test_seed_roster_no_longer_contains_gtwc_or_wec():
    from app.seed import ROSTER

    assert set(ROSTER) == {"imsa-weathertech"}  # F1 now comes from the official roster source


def test_resolve_entries_prefers_the_official_list_over_hand_made_rows():
    import uuid

    ev = uuid.uuid4()

    def row(number, event, source):
        return VehicleEntry(race_number=number, event_id=event, source_name=source)

    seed = [row("1", None, None), row("2", None, None)]
    assert [e.race_number for e in resolve_entries(seed + [row("2", ev, None)], ev)] == ["1", "2"]  # override semantics
    listed = [row("5", ev, "official")]
    assert [e.race_number for e in resolve_entries(seed + listed, ev)] == ["5"]  # the list is complete


async def test_sources_health_reports_entries_separately(client, db, series):
    from datetime import UTC, datetime

    from app.models import SourceRun

    now = datetime.now(UTC)
    for kind, seen in (("schedule", 103), ("entries", 449)):
        db.add(SourceRun(source_id="gt_world_challenge", mode="live", kind=kind, status="success", records_seen=seen,
                         records_changed=1, started_at=now, completed_at=now))
    db.commit()
    health = {h["source_id"]: h for h in client.get("/sources/health").json()}
    gt = health["gt_world_challenge"]
    assert (gt["records_seen"], gt["entries"]["records_seen"], gt["entries"]["status"]) == (103, 449, "healthy")
    assert gt["entries"]["limitation"] and "session assignment" in gt["entries"]["limitation"]
    assert health["fia_wec"]["entries"] is not None
