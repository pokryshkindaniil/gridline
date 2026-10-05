"""Formula 1 season roster from formula1.com: parsing the captured pages, fetching them, storing them, serving them."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
from gridline_sources import EntryFetchPlan, get_source
from gridline_sources.base import SourceError
from gridline_sources.entries import RawEntries
from gridline_sources.formula1 import roster
from sqlalchemy import func, select

from app.models import Driver, DriverAlias, Season, Team, TeamAlias, VehicleEntry, VehicleModel
from app.seed import seed_roster  # noqa: F401
from app.services.entries import apply_parsed_entries
from app.sources import sync as sync_mod

from .conftest import TestSession

DIR = Path(get_source("formula1").entries_dir)
NOW = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)
SRC = "Formula 1 (formula1.com) (season roster)"

EXPECTED = {  # team display name -> (constructor, chassis, {number: driver})
    "Mercedes": ("Mercedes", "W17", {"63": "George Russell", "12": "Kimi Antonelli"}),
    "Ferrari": ("Ferrari", "SF-26", {"16": "Charles Leclerc", "44": "Lewis Hamilton"}),
    "McLaren": ("McLaren", "MCL40", {"1": "Lando Norris", "81": "Oscar Piastri"}),
    "Red Bull Racing": ("Red Bull Racing", "RB22", {"3": "Max Verstappen", "6": "Isack Hadjar"}),
    "Racing Bulls": ("Racing Bulls", "VCARB 03", {"30": "Liam Lawson", "41": "Arvid Lindblad"}),
    "Alpine": ("Alpine", "A526", {"10": "Pierre Gasly", "43": "Franco Colapinto"}),
    "Haas F1 Team": ("Haas", "VF-26", {"31": "Esteban Ocon", "87": "Oliver Bearman"}),
    "Audi": ("Audi", "R26", {"27": "Nico Hulkenberg", "5": "Gabriel Bortoleto"}),
    "Williams": ("Williams", "FW48", {"55": "Carlos Sainz", "23": "Alexander Albon"}),
    "Aston Martin": ("Aston Martin", "AMR26", {"14": "Fernando Alonso", "18": "Lance Stroll"}),
    "Cadillac": ("Cadillac", "MAC-26", {"11": "Sergio Perez", "77": "Valtteri Bottas"}),
}


@pytest.fixture
def f1(monkeypatch):
    src = get_source("formula1")
    monkeypatch.setattr(src, "request_delay", 0)
    monkeypatch.setattr(src, "year", 2026)
    return src


def parsed(f1):
    return f1.parse_entries(f1.load_entries_fixture())


# ------------------------------------------------------------------------------------------------ parsing

def test_the_full_field_is_imported_not_a_subset(f1):
    r = parsed(f1)
    assert r.issues == []
    assert len(r.entries) == 22 and {e.team_name for e in r.entries} == set(EXPECTED)
    assert all(len(e.drivers) == 1 and e.event_external_id is None and e.season_year == 2026 for e in r.entries)


def test_teams_cars_numbers_and_drivers_match_the_official_pages(f1):
    got: dict = {}
    for e in parsed(f1).entries:
        d = e.drivers[0]
        got.setdefault(e.team_name, (e.manufacturer, e.model, {}))[2][e.race_number] = f"{d.first_name} {d.last_name}"
    assert got == EXPECTED


def test_vehicle_model_is_the_published_chassis_and_manufacturer_a_separate_field(f1):
    for e in parsed(f1).entries:
        assert e.model and e.manufacturer and e.model != e.manufacturer
        assert not e.model.startswith(e.manufacturer)  # 'SF-26', not 'Ferrari SF-26': the two are never conflated


def test_source_ids_nationality_birth_date_and_the_team_full_name_are_kept(f1):
    by = {f"{e.drivers[0].first_name} {e.drivers[0].last_name}": e for e in parsed(f1).entries}
    leclerc = by["Charles Leclerc"]
    assert (leclerc.drivers[0].external_id, leclerc.drivers[0].nationality_code, leclerc.drivers[0].birth_date) == ("CHALEC01", "MC", date(1997, 10, 16))
    assert leclerc.team_external_id == "ferrari" and leclerc.team_aliases == ("Scuderia Ferrari HP",)
    assert by["Max Verstappen"].drivers[0].nationality_code == "NL" and by["Nico Hulkenberg"].drivers[0].nationality_code == "DE"
    assert leclerc.source_url == "https://www.formula1.com/en/teams/ferrari"


def test_numbers_are_empty_not_invented_before_the_first_race(f1):
    raw = f1.load_entries_fixture()
    no_results = RawEntries(raw.source_url, raw.fetched_at, {k: v for k, v in raw.documents.items() if not k.startswith("result_")}, is_fixture=True)
    r = f1.parse_entries(no_results)
    assert len(r.entries) == 22 and all(e.race_number is None for e in r.entries)
    assert len(r.issues) == 22 and all("no race number published yet" in i.message for i in r.issues)


def test_the_newest_race_result_wins_when_numbers_change(f1):
    raw = f1.load_entries_fixture()
    docs = dict(raw.documents)
    newest = max((k for k in docs if k.startswith("result_")), key=lambda k: int(k[7:-5]))
    assert "<td" in docs[newest]
    docs[newest] = docs[newest].replace(">16<", ">99<", 1)  # Leclerc's car number changes in the newest result
    r = f1.parse_entries(RawEntries(raw.source_url, raw.fetched_at, docs, is_fixture=True))
    assert {e.drivers[0].last_name: e.race_number for e in r.entries}["Leclerc"] == "99"


def test_one_unreadable_team_is_quarantined_and_the_rest_still_import(f1):
    raw = f1.load_entries_fixture()
    docs = dict(raw.documents)
    docs[roster.team_key("alpine")] = "<!-- FETCH-ERROR GET /en/teams/alpine failed: 503 -->"
    r = f1.parse_entries(RawEntries(raw.source_url, raw.fetched_at, docs, is_fixture=True))
    assert len(r.entries) == 20 and "Alpine" not in {e.team_name for e in r.entries}
    assert [i.event for i in r.issues] == ["alpine"] and "503" in r.issues[0].message


def test_a_team_page_without_chassis_is_quarantined_not_guessed(f1):
    raw = f1.load_entries_fixture()
    docs = dict(raw.documents)
    docs[roster.team_key("williams")] = docs[roster.team_key("williams")].replace("Chassis", "Something else")
    r = f1.parse_entries(RawEntries(raw.source_url, raw.fetched_at, docs, is_fixture=True))
    assert "Williams" not in {e.team_name for e in r.entries} and any("no Chassis" in i.message for i in r.issues)


def test_markup_changes_fail_loudly(f1):
    raw = f1.load_entries_fixture()
    with pytest.raises(SourceError, match="lists no teams"):
        f1.parse_entries(RawEntries(raw.source_url, raw.fetched_at, {**raw.documents, roster.TEAMS_KEY: "<html></html>"}))
    with pytest.raises(SourceError, match="standings"):
        f1.parse_entries(RawEntries(raw.source_url, raw.fetched_at, {**raw.documents, roster.STANDINGS_KEY: "<html></html>"}))


# ------------------------------------------------------------------------------------------------ fetching

def handler(calls: list | None = None, fail: set[str] = frozenset()):
    def h(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if calls is not None:
            calls.append(path)
        if path in fail:
            return httpx.Response(503)
        if path == "/en/teams":
            key = roster.TEAMS_KEY
        elif path.startswith("/en/teams/"):
            key = roster.team_key(path.rsplit("/", 1)[1])
        elif path == "/en/results/2026/drivers":
            key = roster.STANDINGS_KEY
        elif path == "/en/results/2026/races":
            key = roster.RACES_KEY
        elif "/races/" in path and path.endswith("/race-result"):
            key = roster.result_key(path.split("/races/")[1].split("/")[0])
        elif path.startswith("/en/drivers/"):
            key = roster.driver_key(path.rsplit("/", 1)[1])
        else:
            return httpx.Response(404)
        return httpx.Response(200, text=(DIR / key).read_text()) if (DIR / key).exists() else httpx.Response(404)

    return h


async def test_fetch_reads_teams_standings_drivers_and_recent_results_only(f1, monkeypatch):
    calls: list = []
    monkeypatch.setattr(f1, "transport", httpx.MockTransport(handler(calls)))
    raw = await f1.fetch_entries(EntryFetchPlan())
    assert len(f1.parse_entries(raw).entries) == 22 and not raw.is_fixture
    assert calls[0] == "/en/teams" and "/en/results/2026/drivers" in calls
    assert sum(p.startswith("/en/teams/") for p in calls) == 11 and sum(p.startswith("/en/drivers/") for p in calls) == 22
    assert sum("/race-result" in p for p in calls) <= roster.MAX_RESULT_PAGES  # never the whole season


async def test_a_team_page_failing_quarantines_that_team_only(f1, monkeypatch):
    monkeypatch.setattr(f1, "transport", httpx.MockTransport(handler(fail={"/en/teams/cadillac"})))
    raw = await f1.fetch_entries(EntryFetchPlan())
    r = f1.parse_entries(raw)
    assert len(r.entries) == 20 and any(i.event == "cadillac" for i in r.issues)


async def test_the_index_or_standings_failing_fails_the_whole_fetch(f1, monkeypatch):
    for dead in ("/en/teams", "/en/results/2026/drivers"):
        monkeypatch.setattr(f1, "transport", httpx.MockTransport(handler(fail={dead})))
        with pytest.raises(SourceError):
            await f1.fetch_entries(EntryFetchPlan())


async def test_no_race_results_yet_still_yields_the_roster_without_numbers(f1, monkeypatch):
    monkeypatch.setattr(f1, "transport", httpx.MockTransport(handler(fail={"/en/results/2026/races"})))
    r = f1.parse_entries(await f1.fetch_entries(EntryFetchPlan()))
    assert len(r.entries) == 22 and all(e.race_number is None for e in r.entries)


# ------------------------------------------------------------------------------------------------ database

@pytest.fixture
def f1_world(db, series):
    s = series["formula-1"]
    db.add(Season(series_id=s.id, year=2026))
    db.commit()
    return s


def sync(db, s, f1, now=NOW, name=SRC):
    stats = apply_parsed_entries(db, s, parsed(f1).entries, source_name=name, now=now, source_id="formula1")
    db.commit()
    return stats


def test_roster_is_stored_with_teams_drivers_numbers_models_and_provenance(db, f1_world, f1):
    stats = sync(db, f1_world, f1)
    assert (stats.inserted, stats.updated, stats.removed) == (22, 0, 0)
    assert db.scalar(select(func.count(Team.id))) == 11 and db.scalar(select(func.count(Driver.id))) == 22
    rows = db.scalars(select(VehicleEntry)).all()
    assert len(rows) == 22 and all(r.event_id is None and r.source_name == SRC and r.checked_at == NOW for r in rows)
    assert all(r.source_url.startswith("https://www.formula1.com/en/teams/") for r in rows)
    ferrari = db.scalar(select(Team).where(Team.slug == "ferrari"))
    cars = sorted((e.race_number, e.manufacturer_ref.canonical_name, e.vehicle_model.canonical_name) for e in db.scalars(select(VehicleEntry).where(VehicleEntry.team_id == ferrari.id)))
    assert cars == [("16", "Ferrari", "SF-26"), ("44", "Ferrari", "SF-26")]
    sf26 = db.scalar(select(VehicleModel).where(VehicleModel.slug == "sf-26"))
    assert (sf26.season_year, sf26.category, sf26.manufacturer.slug) == (2026, "Formula 1", "ferrari")
    assert {t.name for t in db.scalars(select(Team))} == set(EXPECTED)


def test_drivers_are_linked_through_the_entry_and_carry_source_ids(db, f1_world, f1):
    sync(db, f1_world, f1)
    leclerc = db.scalar(select(Driver).where(Driver.slug == "charles-leclerc"))
    assert (leclerc.nationality_code, leclerc.birth_date) == ("MC", date(1997, 10, 16))
    assert [(e.race_number, e.team.name) for e in db.scalars(select(VehicleEntry).join(VehicleEntry.drivers).where(VehicleEntry.drivers.any(driver_id=leclerc.id)))] == [("16", "Ferrari")]
    alias = db.scalar(select(DriverAlias).where(DriverAlias.driver_id == leclerc.id))
    assert (alias.source_name, alias.source_external_id) == ("formula1", "CHALEC01")
    full = db.scalar(select(TeamAlias).where(TeamAlias.source_value == "Scuderia Ferrari HP"))
    assert full.team.slug == "ferrari" and full.source_name == "formula1"


def test_a_second_run_changes_nothing_and_a_renumbering_updates_in_place(db, f1_world, f1):
    sync(db, f1_world, f1)
    assert (lambda s: (s.inserted, s.updated, s.removed))(sync(db, f1_world, f1)) == (0, 0, 0)
    entries = parsed(f1).entries
    from dataclasses import replace
    changed = [replace(e, race_number="99") if e.race_number == "16" else e for e in entries]
    stats = apply_parsed_entries(db, f1_world, changed, source_name=SRC, now=NOW, source_id="formula1")
    db.commit()
    assert stats.updated == 1 and stats.inserted == 0 and "number 16 -> 99" in stats.changes[0]
    assert db.scalar(select(func.count(VehicleEntry.id))) == 22


def test_the_live_roster_adopts_the_development_seed_rows_instead_of_duplicating_them(db, f1_world, f1):
    # a dev seed from before the official source existed: Ferrari #44 (Hamilton) and a stale #99
    ferrari = Team(series_id=f1_world.id, slug="ferrari", name="Ferrari")
    ham = Driver(slug="lewis-hamilton", first_name="Lewis", last_name="Hamilton")
    db.add_all([ferrari, ham])
    db.flush()
    season = db.scalar(select(Season))
    from app.models import VehicleEntryDriver
    for n, drv in (("44", ham), ("99", None)):
        e = VehicleEntry(team_id=ferrari.id, season_id=season.id, race_number=n, manufacturer="Ferrari", model="SF-26")
        db.add(e)
        db.flush()
        if drv:
            db.add(VehicleEntryDriver(vehicle_entry_id=e.id, driver_id=drv.id))
    db.commit()
    stats = sync(db, f1_world, f1)
    assert stats.removed == 1 and any("#99: removed" in c for c in stats.changes)  # stale seed row of a listed team goes
    rows = db.scalars(select(VehicleEntry).where(VehicleEntry.team_id == ferrari.id)).all()
    assert sorted(r.race_number for r in rows) == ["16", "44"] and all(r.source_name == SRC for r in rows)
    assert db.scalar(select(func.count(Driver.id)).where(Driver.slug == "lewis-hamilton")) == 1  # same person, no duplicate


def test_a_fixture_never_overwrites_a_live_roster(db, f1_world, f1):
    sync(db, f1_world, f1)
    from dataclasses import replace
    stale = [replace(e, race_number=str(100 + i)) for i, e in enumerate(parsed(f1).entries)]
    stats = apply_parsed_entries(db, f1_world, stale, source_name=SRC.replace(")", ", fixture snapshot)"), now=NOW, source_id="formula1")
    db.commit()
    assert any("kept 22 roster entries from a live source" in w for w in stats.warnings)
    assert {r.race_number for r in db.scalars(select(VehicleEntry))} >= {"16", "44"}


def test_a_partial_roster_only_touches_the_teams_it_lists(db, f1_world, f1):
    sync(db, f1_world, f1)
    few = parsed(f1).entries[:4]  # Mercedes and Ferrari only
    stats = apply_parsed_entries(db, f1_world, few, source_name=SRC, now=NOW, source_id="formula1")
    db.commit()
    assert (stats.inserted, stats.updated, stats.removed) == (0, 0, 0) and db.scalar(select(func.count(VehicleEntry.id))) == 22


async def test_run_sync_applies_the_f1_roster_after_the_schedule(db, series, f1):
    results = await sync_mod.run_sync(["formula1"], fixtures=True, db_factory=TestSession)
    assert [(r.kind, r.status) for r in results] == [("schedule", "success"), ("entries", "success")]
    assert db.scalar(select(func.count(VehicleEntry.id))) == 22
    assert db.scalar(select(VehicleEntry.source_name)) == "Formula 1 (formula1.com) (season roster, fixture snapshot)"


# ------------------------------------------------------------------------------------------------ API

@pytest.fixture
def f1_synced(db, f1_world, f1):
    sync(db, f1_world, f1)
    return f1_world


def test_teams_api_serves_manufacturer_and_vehicle_model_separately_with_provenance(client, f1_synced):
    teams = {t["name"]: t for t in client.get("/series/formula-1/teams").json()}
    assert set(teams) == set(EXPECTED)
    ferrari = teams["Ferrari"]
    assert [e["race_number"] for e in ferrari["entries"]] == ["16", "44"]
    v = ferrari["entries"][0]["vehicle"]
    assert (v["manufacturer"], v["manufacturer_slug"], v["model"], v["model_slug"]) == ("Ferrari", "ferrari", "SF-26", "sf-26")
    assert [d["slug"] for e in ferrari["entries"] for d in e["drivers"]] == ["charles-leclerc", "lewis-hamilton"]
    assert ferrari["source_name"] == SRC and ferrari["source_url"].endswith("/en/teams/ferrari") and ferrari["checked_at"]
    assert teams["Aston Martin"]["entries"][0]["vehicle"]["model"] == "AMR26"
    assert client.get("/series/formula-1/entry-events").json() == []  # a season roster, not per-event lists


def test_team_detail_carries_the_same_vehicle_data_and_resolves_by_series(client, f1_synced):
    t = client.get("/teams/ferrari", params={"series": "formula-1"}).json()
    assert t["vehicle"]["model"] == "SF-26" and t["entries"][1]["vehicle"]["race_number"] == "44"
    assert client.get("/teams/ferrari", params={"series": "fia-wec"}).status_code == 404


def test_a_missing_model_shows_the_manufacturer_only_and_nothing_is_invented(client, db, f1_synced):
    for e in db.scalars(select(VehicleEntry)):
        e.model, e.vehicle_model_id = None, None
    db.commit()
    v = client.get("/teams/ferrari", params={"series": "formula-1"}).json()["entries"][0]["vehicle"]
    assert (v["manufacturer"], v["model"], v["model_slug"]) == ("Ferrari", None, None)


def test_entries_without_canonical_links_still_serve_the_source_spelling(client, db, f1_synced):
    for e in db.scalars(select(VehicleEntry)):
        e.manufacturer_id, e.vehicle_model_id = None, None  # e.g. rows created before identity existed
    db.commit()
    v = client.get("/teams/ferrari", params={"series": "formula-1"}).json()["entries"][0]["vehicle"]
    assert (v["manufacturer"], v["model"], v["manufacturer_slug"]) == ("Ferrari", "SF-26", None)
