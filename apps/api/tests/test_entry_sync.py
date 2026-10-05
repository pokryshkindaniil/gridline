"""Entry-list sync: applying parsed entries to the database, and the safety rules around it."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from gridline_sources import EntryParseResult, ParsedDriver, ParsedEntry, SourceIssue
from sqlalchemy import func, select

from app.models import Driver, Event, Season, SourceRun, Team, VehicleEntry
from app.services.entries import apply_parsed_entries
from app.sources import sync as sync_mod

from .conftest import TestSession
from .helpers import FakeEntrySource

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
SRC = "GT World Challenge Europe (SRO) (entry list)"


def drv(name: str, nat: str | None = "GB") -> ParsedDriver:
    first, last = name.split(" ", 1)
    return ParsedDriver(first, last, nat)


def pe(event: str, number: str, team: str, drivers: list[str], *, cls: str = "Pro", model: str = "M4 GT3 EVO",
       make: str | None = "BMW", cup: str | None = "Sprint Cup", url: str | None = None) -> ParsedEntry:
    return ParsedEntry(season_year=2026, event_external_id=event, race_number=number, team_name=team,
                       drivers=tuple(drv(d) for d in drivers), source_url=url or f"https://example.org/{event}",
                       manufacturer=make, model=model, class_name=cls, competition=cup)


@pytest.fixture
def world(db, series):
    gt = series["gt-world-challenge-europe"]
    season = Season(series_id=gt.id, year=2026)
    db.add(season)
    db.flush()
    evs = {}
    for i, key in enumerate(("e1", "e2", "e3")):
        evs[key] = Event(season_id=season.id, external_id=key, slug=f"event-{key}", name=f"Event {key}",
                         timezone="Europe/Madrid", start_date=date(2026, 5 + i, 1), end_date=date(2026, 5 + i, 3))
        db.add(evs[key])
    db.commit()
    return dict(series=gt, season=season, events=evs)


def apply(db, world, entries, source_name=SRC, now=NOW):
    stats = apply_parsed_entries(db, world["series"], entries, source_name=source_name, now=now)
    db.commit()
    return stats


def grid(db, event) -> dict[str, tuple[str, list[str], str | None]]:
    """{number: (team, [driver slugs in order], class)} for one event."""
    rows = db.scalars(select(VehicleEntry).where(VehicleEntry.event_id == event.id)).all()
    return {r.race_number: (r.team.name, [d.driver.slug for d in r.drivers], r.class_name) for r in rows}


def test_first_sync_creates_teams_drivers_and_event_entries_with_provenance(db, world):
    s = apply(db, world, [pe("e1", "32", "Team WRT", ["Charles Weerts", "Dries Vanthoor"]),
                          pe("e1", "46", "Team WRT", ["Valentino Rossi", "Max Hesse"])])
    assert (s.inserted, s.updated, s.removed, s.events_applied) == (2, 0, 0, 1)
    assert grid(db, world["events"]["e1"]) == {
        "32": ("Team WRT", ["charles-weerts", "dries-vanthoor"], "Pro"),
        "46": ("Team WRT", ["valentino-rossi", "max-hesse"], "Pro")}
    assert db.scalar(select(func.count(Team.id))) == 1  # one team, two cars
    row = db.scalar(select(VehicleEntry).where(VehicleEntry.race_number == "32"))
    assert (row.source_name, row.source_url, row.checked_at, row.competition) == (SRC, "https://example.org/e1", NOW, "Sprint Cup")
    assert [d.position for d in row.drivers] == [0, 1]


def test_resync_without_changes_changes_nothing_but_freshness(db, world):
    entries = [pe("e1", "32", "Team WRT", ["Charles Weerts", "Dries Vanthoor"])]
    apply(db, world, entries)
    later = NOW + timedelta(hours=1)
    s = apply(db, world, entries, now=later)
    assert s.changed == 0 and s.changes == []
    assert db.scalar(select(VehicleEntry.checked_at)) == later


def test_driver_added(db, world):
    apply(db, world, [pe("e1", "5", "Optimum", ["A One", "B Two"], cup="Endurance Cup")])
    s = apply(db, world, [pe("e1", "5", "Optimum", ["A One", "B Two", "C Three"], cup="Endurance Cup")])
    assert s.updated == 1 and "drivers a-one, b-two -> a-one, b-two, c-three" in s.changes[0]
    assert grid(db, world["events"]["e1"])["5"][1] == ["a-one", "b-two", "c-three"]


def test_driver_removed_keeps_the_driver_record_but_not_the_seat(db, world):
    apply(db, world, [pe("e1", "5", "Optimum", ["A One", "B Two", "C Three"])])
    s = apply(db, world, [pe("e1", "5", "Optimum", ["A One", "C Three"])])
    assert s.updated == 1
    assert grid(db, world["events"]["e1"])["5"][1] == ["a-one", "c-three"]
    assert db.scalar(select(Driver.id).where(Driver.slug == "b-two")) is not None  # still known, just not entered


def test_substitute_driver_replaces_in_place_and_keeps_position(db, world):
    apply(db, world, [pe("e1", "12", "Jota", ["W Stevens", "N Nato", "L Deletraz"])])
    s = apply(db, world, [pe("e1", "12", "Jota", ["W Stevens", "N Nato", "R Taylor"])])
    assert (s.inserted, s.updated, s.removed) == (0, 1, 0)
    assert grid(db, world["events"]["e1"])["12"][1] == ["w-stevens", "n-nato", "r-taylor"]
    assert db.scalar(select(func.count(VehicleEntry.id))) == 1


def test_published_order_change_is_an_update(db, world):
    apply(db, world, [pe("e1", "7", "T", ["A One", "B Two"])])
    s = apply(db, world, [pe("e1", "7", "T", ["B Two", "A One"])])
    assert s.updated == 1 and grid(db, world["events"]["e1"])["7"][1] == ["b-two", "a-one"]


def test_race_number_change_is_a_removal_plus_an_insertion(db, world):
    apply(db, world, [pe("e1", "12", "Jota", ["A One", "B Two"])])
    s = apply(db, world, [pe("e1", "112", "Jota", ["A One", "B Two"])])
    assert (s.inserted, s.updated, s.removed) == (1, 0, 1)
    assert list(grid(db, world["events"]["e1"])) == ["112"]


def test_class_make_model_and_team_changes_update_in_place(db, world):
    apply(db, world, [pe("e1", "51", "AF Corse", ["A One", "B Two"], cls="Gold", model="296 GT3 EVO")])
    s = apply(db, world, [pe("e1", "51", "Iron Lynx", ["A One", "B Two"], cls="Pro", model="296 GT3 EVO II")])
    assert s.updated == 1 and s.inserted == s.removed == 0
    note = s.changes[0]
    assert "class Gold -> Pro" in note and "model 296 GT3 EVO -> 296 GT3 EVO II" in note and "team -> Iron Lynx" in note
    assert grid(db, world["events"]["e1"])["51"] == ("Iron Lynx", ["a-one", "b-two"], "Pro")


def test_lineups_are_per_event_and_never_leak_between_events(db, world):
    apply(db, world, [
        pe("e1", "2", "Boutsen VDS", ["Sven Muller", "Dorian Boccolacci"]),
        pe("e2", "2", "Boutsen VDS", ["Dorian Boccolacci", "Morris Schuring"]),
        pe("e3", "2", "Boutsen VDS", ["Alessio Picariello", "Dorian Boccolacci"]),
    ])
    ev = world["events"]
    assert grid(db, ev["e1"])["2"][1] == ["sven-muller", "dorian-boccolacci"]
    assert grid(db, ev["e2"])["2"][1] == ["dorian-boccolacci", "morris-schuring"]
    # now e2 changes; e1 and e3 stay exactly as they were
    apply(db, world, [pe("e2", "2", "Boutsen VDS", ["Dorian Boccolacci", "Jules Gounon"])])
    assert grid(db, ev["e1"])["2"][1] == ["sven-muller", "dorian-boccolacci"]
    assert grid(db, ev["e2"])["2"][1] == ["dorian-boccolacci", "jules-gounon"]
    assert grid(db, ev["e3"])["2"][1] == ["alessio-picariello", "dorian-boccolacci"]
    assert db.scalar(select(func.count(Team.id))) == 1  # the team is shared across events


def test_cars_missing_from_the_new_list_are_removed(db, world):
    apply(db, world, [pe("e1", str(n), "T", ["A One", "B Two"]) for n in range(1, 5)])
    s = apply(db, world, [pe("e1", str(n), "T", ["A One", "B Two"]) for n in range(1, 4)])
    assert s.removed == 1 and sorted(grid(db, world["events"]["e1"])) == ["1", "2", "3"]


def test_shrinking_list_is_treated_as_damage_and_left_alone(db, world):
    apply(db, world, [pe("e1", str(n), "T", ["A One", "B Two"]) for n in range(1, 11)])
    s = apply(db, world, [pe("e1", "1", "T", ["A One", "B Two"])])
    assert s.changed == 0 and any("source lists 1 of 10" in w for w in s.warnings)
    assert len(grid(db, world["events"]["e1"])) == 10


def test_event_not_in_schedule_is_skipped_with_a_warning(db, world):
    s = apply(db, world, [pe("nope", "1", "T", ["A One"]), pe("e1", "1", "T", ["A One"])])
    assert s.inserted == 1 and any("nope" in w and "not in the schedule" in w for w in s.warnings)


def test_duplicate_numbers_in_a_list_skip_that_event_only(db, world):
    s = apply(db, world, [pe("e1", "1", "T", ["A One"]), pe("e1", "1", "U", ["B Two"]), pe("e2", "1", "T", ["A One"])])
    assert s.inserted == 1 and grid(db, world["events"]["e1"]) == {} and "e2" not in str(s.warnings)


def test_fixture_data_never_overwrites_live_data(db, world):
    live = "GT World Challenge Europe (SRO) (entry list)"
    fixture = "GT World Challenge Europe (SRO) (entry list, fixture snapshot)"
    apply(db, world, [pe("e1", "1", "T", ["Real Driver", "Other Driver"])], source_name=live)
    s = apply(db, world, [pe("e1", "1", "T", ["Fixture Driver", "Other Driver"]), pe("e2", "1", "T", ["F Two"])], source_name=fixture)
    assert grid(db, world["events"]["e1"])["1"][1] == ["real-driver", "other-driver"]
    assert any("fixture data ignored" in w for w in s.warnings)
    assert grid(db, world["events"]["e2"])["1"][1] == ["f-two"]  # no live data for e2: fixture may fill it
    # and live data replaces fixture data
    apply(db, world, [pe("e2", "1", "T", ["Real Two"])], source_name=live)
    assert grid(db, world["events"]["e2"])["1"][1] == ["real-two"]


def test_a_database_failure_inside_one_event_leaves_the_others_applied(db, world, monkeypatch):
    from app.services import entries as svc

    real = svc._apply_event

    def flaky(db_, cache, series_, event, season, incoming, source_name, now, stats):
        real(db_, cache, series_, event, season, incoming, source_name, now, stats)
        if event.external_id == "e2":
            raise RuntimeError("constraint exploded")

    monkeypatch.setattr(svc, "_apply_event", flaky)
    s = apply(db, world, [pe("e1", "1", "T", ["A One"]), pe("e2", "1", "T", ["B Two"])])
    assert grid(db, world["events"]["e2"]) == {} and list(grid(db, world["events"]["e1"])) == ["1"]
    assert (s.inserted, s.events_applied) == (1, 1) and any("e2" in w and "left unchanged" in w for w in s.warnings)


def test_hand_made_season_wide_rows_are_never_touched(db, world):
    team = Team(series_id=world["series"].id, slug="seed-team", name="Seed Team")
    db.add(team)
    db.flush()
    db.add(VehicleEntry(team_id=team.id, season_id=world["season"].id, race_number="99", model="X"))
    db.commit()
    apply(db, world, [pe("e1", "1", "T", ["A One"])])
    assert db.scalar(select(func.count(VehicleEntry.id)).where(VehicleEntry.event_id.is_(None))) == 1


def test_nationality_is_filled_in_but_never_erased(db, world):
    apply(db, world, [pe("e1", "1", "T", ["A One"])])
    p = pe("e1", "1", "T", ["A One"])
    p = ParsedEntry(**{**p.__dict__, "drivers": (ParsedDriver("A", "One", None),)})
    apply(db, world, [p])
    assert db.scalar(select(Driver.nationality_code).where(Driver.slug == "a-one")) == "GB"


# ------------------------------------------------------------------------------------------ sync runs

def result(*entries, issues=()):
    return EntryParseResult(list(entries), list(issues), {e.event_external_id for e in entries})


async def run(source, **kw):
    return await sync_mod.sync_entries(source, db_factory=TestSession, now=NOW, **kw)


async def test_sync_records_a_separate_entries_run(db, world):
    r = await run(FakeEntrySource(result(pe("e1", "1", "T", ["A One", "B Two"]))))
    assert (r.status, r.kind, r.entry_stats.inserted) == ("success", "entries", 1)
    run_row = db.scalar(select(SourceRun))
    assert (run_row.kind, run_row.status, run_row.records_seen, run_row.records_changed) == ("entries", "success", 1, 1)
    row = db.scalar(select(VehicleEntry))
    assert row.source_name == "Fake source (entry list)"


async def test_zero_entries_after_failures_never_wipes_existing_entries(db, world):
    apply(db, world, [pe("e1", "1", "T", ["A One", "B Two"]), pe("e1", "2", "T", ["C Three", "D Four"])])
    broken = result(issues=[SourceIssue("event-1", "SourceError: entry table is empty")])
    r = await run(FakeEntrySource(broken))
    assert r.status == "failed" and "keeping existing entries" in r.error
    assert len(grid(db, world["events"]["e1"])) == 2


async def test_parser_crash_and_fetch_failure_keep_existing_entries(db, world):
    apply(db, world, [pe("e1", "1", "T", ["A One"])])
    for src in (FakeEntrySource(RuntimeError("boom")), FakeEntrySource(fetch_error=RuntimeError("net down"))):
        r = await run(src)
        assert r.status == "failed"
    assert len(grid(db, world["events"]["e1"])) == 1


async def test_nothing_to_do_is_a_success_not_a_failure(db, world):
    r = await run(FakeEntrySource(result()))
    assert r.status == "success" and r.entry_stats.seen == 0


async def test_one_quarantined_event_does_not_block_the_others(db, world):
    apply(db, world, [pe("e2", "1", "T", ["Old Driver"])])
    src = FakeEntrySource(result(pe("e1", "1", "T", ["A One"]),
                                 issues=[SourceIssue("e2", "SourceError: cannot split driver name 'x'")]))
    r = await run(src)
    assert r.status == "partial" and any("e2" in i for i in r.issues)
    assert len(grid(db, world["events"]["e1"])) == 1
    assert grid(db, world["events"]["e2"])["1"][1] == ["old-driver"]  # quarantined event left as stored


async def test_settled_events_are_not_refetched_but_recent_and_fixture_ones_are(db, world):
    live = "Fake source (entry list)"
    apply(db, world, [pe("e1", "1", "T", ["A One"]), pe("e3", "1", "T", ["A One"])], source_name=live)
    fixture_only = pe("e2", "1", "T", ["A One"])
    apply(db, world, [fixture_only], source_name=live + ", fixture snapshot")
    src = FakeEntrySource(result())
    # e1 ended 2026-05-03, e2 2026-06-03, e3 2026-07-03; "now" is 2026-10-04: all are older than 14 days
    await run(src)
    assert src.plans[-1].settled_events == frozenset({"e1", "e3"})  # e2 only holds fixture data: still wanted
    r2 = await sync_mod.sync_entries(src, db_factory=TestSession, now=datetime(2026, 7, 10, tzinfo=UTC))
    assert r2.status == "success" and src.plans[-1].settled_events == frozenset({"e1"})  # e3 ended 7 days earlier


async def test_fixture_mode_is_labelled_and_sources_without_the_capability_are_ignored(db, world):
    src = FakeEntrySource(result(pe("e1", "1", "T", ["A One"])))
    r = await run(src, fixtures=True)
    assert r.status == "success"
    assert db.scalar(select(VehicleEntry.source_name)) == "Fake source (entry list, fixture snapshot)"
    from .helpers import FakeSource
    assert await sync_mod.sync_entries(FakeSource(), db_factory=TestSession) is None


async def test_sources_without_a_live_adapter_are_skipped_in_live_mode(db, world):
    src = FakeEntrySource(result())
    src.live = False
    assert (await run(src)).status == "skipped"


async def test_run_sync_syncs_entries_after_the_schedule_for_capable_sources(db, series):
    results = await sync_mod.run_sync(["gt_world_challenge"], fixtures=True, db_factory=TestSession)
    assert [(r.source_id, r.kind, r.status) for r in results] == [
        ("gt_world_challenge", "schedule", "success"), ("gt_world_challenge", "entries", "success")]
    assert db.scalar(select(func.count(VehicleEntry.id)).where(VehicleEntry.event_id.is_not(None))) == 449
    assert db.scalar(select(func.count(Team.id))) == 53  # GetSpeed "BartoneBros" is the curated alias of "Bartone Bros"
    # idempotent
    again = await sync_mod.run_sync(["gt_world_challenge"], fixtures=True, db_factory=TestSession)
    assert again[1].entry_stats.changed == 0
