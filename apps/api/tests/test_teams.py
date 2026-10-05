"""Team / entry / driver model: Formula (1 car per driver), endurance (multi-car, 2-4 drivers) and substitutes."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Driver, Event, Season, Team, VehicleEntry, VehicleEntryDriver


def drivers(db, *names):
    out = []
    for n in names:
        first, last = n.split(" ", 1)
        d = Driver(slug=n.lower().replace(" ", "-"), first_name=first, last_name=last, nationality_code="GB")
        db.add(d)
        out.append(d)
    db.flush()
    return out


def entry(db, team, season, number, model, drvs, event=None, manufacturer=None):
    e = VehicleEntry(team_id=team.id, season_id=season.id, event_id=event.id if event else None, race_number=number,
                     manufacturer=manufacturer or team.name, model=model)
    db.add(e)
    db.flush()
    for i, d in enumerate(drvs):
        db.add(VehicleEntryDriver(vehicle_entry_id=e.id, driver_id=d.id, position=i, role="driver"))
    db.flush()
    return e


@pytest.fixture
def grid(db, series):
    f1, wec = series["formula-1"], series["fia-wec"]
    s1, s2 = Season(series_id=f1.id, year=2026), Season(series_id=wec.id, year=2026)
    db.add_all([s1, s2])
    db.flush()
    ev = Event(season_id=s2.id, slug="spa", name="Spa", timezone="Europe/Brussels", external_id="spa",
               start_date="2026-05-07", end_date="2026-05-09")
    db.add(ev)
    ferrari = Team(series_id=f1.id, slug="ferrari", name="Ferrari")
    af = Team(series_id=wec.id, slug="ferrari-af-corse", name="Ferrari AF Corse")
    db.add_all([ferrari, af])
    db.flush()
    ham, lec, fuoco, molina, nielsen, pg, cal, gio, sub = drivers(
        db, "Lewis Hamilton", "Charles Leclerc", "Antonio Fuoco", "Miguel Molina", "Nicklas Nielsen",
        "Alessandro Pier Guidi", "James Calado", "Antonio Giovinazzi", "Sub Driver")
    entry(db, ferrari, s1, "44", "SF-26", [ham], manufacturer="Ferrari")
    entry(db, ferrari, s1, "16", "SF-26", [lec], manufacturer="Ferrari")
    entry(db, af, s2, "50", "499P", [fuoco, molina, nielsen], manufacturer="Ferrari")
    entry(db, af, s2, "51", "499P", [pg, cal, gio], manufacturer="Ferrari")
    db.commit()
    return dict(s1=s1, s2=s2, af=af, ev=ev, sub=sub, cal=cal, gio=gio, pg=pg)


def test_formula_team_has_one_model_and_two_primary_drivers(client, grid):
    team = client.get("/teams/ferrari").json()
    assert {e["vehicle"]["model"] for e in team["entries"]} == {"SF-26"}
    assert [(e["race_number"], [d["last_name"] for d in e["drivers"]]) for e in team["entries"]] == [
        ("16", ["Leclerc"]), ("44", ["Hamilton"])]
    assert team["vehicle"]["model"] == "SF-26"


def test_endurance_entrant_has_multiple_cars_with_three_drivers_each(client, grid):
    teams = client.get("/series/fia-wec/teams").json()
    assert len(teams) == 1 and teams[0]["name"] == "Ferrari AF Corse"
    entries = {e["race_number"]: e for e in teams[0]["entries"]}
    assert set(entries) == {"50", "51"}
    assert [d["last_name"] for d in entries["50"]["drivers"]] == ["Fuoco", "Molina", "Nielsen"]  # position order
    assert all(len(e["drivers"]) == 3 for e in entries.values())


def test_four_driver_entry_is_supported(client, db, grid):
    entry(db, grid["af"], grid["s2"], "83", "499P", drivers(db, "A One", "B Two", "C Three", "D Four"))
    db.commit()
    e = next(e for e in client.get("/teams/ferrari-af-corse").json()["entries"] if e["race_number"] == "83")
    assert len(e["drivers"]) == 4


def test_event_specific_substitute_overrides_only_that_event(client, db, grid):
    entry(db, grid["af"], grid["s2"], "51", "499P", [grid["pg"], grid["cal"], grid["sub"]], event=grid["ev"])
    db.commit()

    def car51(url):
        entries = client.get(url).json()["entries"] if "/teams/" in url else client.get(url).json()[0]["entries"]
        return next(e for e in entries if e["race_number"] == "51")

    season_wide = [d["last_name"] for d in car51("/teams/ferrari-af-corse")["drivers"]]
    at_spa = [d["last_name"] for d in car51(f"/teams/ferrari-af-corse?event_id={grid['ev'].id}")["drivers"]]
    assert season_wide == ["Pier Guidi", "Calado", "Giovinazzi"]
    assert at_spa == ["Pier Guidi", "Calado", "Driver"]
    assert [d["last_name"] for d in car51(f"/series/fia-wec/teams?event_id={grid['ev'].id}")["drivers"]][-1] == "Driver"
    assert len(client.get(f"/teams/ferrari-af-corse?event_id={grid['ev'].id}").json()["entries"]) == 2  # not 3


def test_duplicate_entry_numbers_are_rejected(db, grid):
    with pytest.raises(IntegrityError):
        entry(db, grid["af"], grid["s2"], "50", "499P", [])
    db.rollback()


def test_same_driver_cannot_appear_twice_in_one_entry(db, grid):
    e = db.scalar(select(VehicleEntry).where(VehicleEntry.race_number == "50"))
    with pytest.raises(IntegrityError):
        db.add(VehicleEntryDriver(vehicle_entry_id=e.id, driver_id=e.drivers[0].driver_id, position=9))
        db.flush()
    db.rollback()


def test_deleting_a_team_removes_entries_and_assignments_but_not_drivers(db, grid):
    db.delete(grid["af"])
    db.commit()
    assert db.scalar(select(VehicleEntry).where(VehicleEntry.race_number == "50")) is None
    assert db.scalar(select(VehicleEntryDriver).join(VehicleEntry, isouter=True).where(VehicleEntry.id.is_(None))) is None
    assert db.scalar(select(Driver).where(Driver.slug == "antonio-fuoco")) is not None
