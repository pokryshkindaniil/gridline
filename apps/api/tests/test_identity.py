"""Canonical identity: aliases resolve to one entity, nothing merges by similarity, provenance survives."""

from __future__ import annotations

from datetime import UTC, date, datetime

from gridline_shared import normalize_name
from gridline_shared.aliases import DRIVER_ALIASES, TEAM_ALIASES
from gridline_sources import ParsedDriver, ParsedEntry
from sqlalchemy import func, select

from app.identity_report import build_report, format_report
from app.models import (
    Driver,
    DriverAlias,
    Event,
    Manufacturer,
    Season,
    Team,
    TeamAlias,
    VehicleEntry,
    VehicleModel,
)
from app.services.entries import apply_parsed_entries
from app.services.identity import Resolver, apply_curated, backfill, ensure_identity

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
GTWC, WEC = "gt_world_challenge", "fia_wec"


def pd(first: str, last: str, **kw) -> ParsedDriver:
    return ParsedDriver(first, last, **kw)


def entry(event: str, number: str, team: str, drivers: list[ParsedDriver], make="Ferrari", model="296 GT3 EVO") -> ParsedEntry:
    return ParsedEntry(season_year=2026, event_external_id=event, race_number=number, team_name=team, drivers=tuple(drivers),
                       source_url="https://example.org/" + event, manufacturer=make, model=model, class_name="Pro")


def world(db, series, slug="gt-world-challenge-europe", events=("e1", "e2")):
    s = series[slug]
    season = Season(series_id=s.id, year=2026)
    db.add(season)
    db.flush()
    for i, key in enumerate(events):
        db.add(Event(season_id=season.id, external_id=key, slug=key, name=key, timezone="UTC",
                     start_date=date(2026, 5 + i, 1), end_date=date(2026, 5 + i, 3)))
    db.commit()
    return s


# ---------------------------------------------------------------------------------------------- normalisation

def test_normalisation_folds_case_whitespace_and_punctuation_but_keeps_accents():
    assert normalize_name("  Mercedes - AMG  Team ") == normalize_name("MERCEDES-AMG TEAM") == "mercedes amg team"
    assert normalize_name("O'Ward") == normalize_name("O’Ward") == normalize_name("o ward")
    assert normalize_name("Sven Müller") != normalize_name("Sven Muller")  # accents are meaningful: never erased here
    assert normalize_name("Straße") == normalize_name("STRASSE") or normalize_name("Straße") == "straße"
    assert normalize_name("Dani Juncadella") != normalize_name("Daniel Juncadella")  # no nicknames, no fuzziness


# ---------------------------------------------------------------------------------------------- drivers

def test_an_explicit_alias_resolves_both_spellings_to_one_canonical_driver_and_keeps_the_source_spelling(db, series):
    s = world(db, series)
    r = Resolver(db, s, GTWC, NOW)
    a = r.driver(pd("Dani", "Juncadella"))
    b = r.driver(pd("Daniel", "Juncadella"))
    db.commit()
    assert a.id == b.id and a.canonical_name == "Daniel Juncadella" and a.slug == "daniel-juncadella"
    spellings = {x.source_value: x.source_name for x in db.scalars(select(DriverAlias).where(DriverAlias.driver_id == a.id))}
    assert spellings == {"Dani Juncadella": GTWC, "Daniel Juncadella": GTWC}  # exact source spelling is provenance


def test_a_source_typo_maps_through_its_explicit_alias_only(db, series):
    s = world(db, series)
    r = Resolver(db, s, GTWC, NOW)
    assert r.driver(pd("Niclkas", "Nielsen")).canonical_name == "Nicklas Nielsen"
    # the same typo from a source the alias does not name is NOT silently fixed: it becomes its own driver
    other = Resolver(db, s, WEC, NOW).driver(pd("Niclkas", "Nielsen"))
    assert other.canonical_name == "Niclkas Nielsen"


def test_aliases_are_source_aware(db, series):
    s = world(db, series)
    wec_series = series["fia-wec"]
    jonathan_wec = Resolver(db, wec_series, WEC, NOW).driver(pd("Jonathan", "Adam"))   # alias names GTWC only
    jonathan_gtwc = Resolver(db, s, GTWC, NOW).driver(pd("Jonathan", "Adam"))
    assert jonathan_gtwc.canonical_name == "Jonny Adam" and jonathan_wec.id != jonathan_gtwc.id


def test_same_surname_different_people_never_merge(db, series):
    s = world(db, series)
    r = Resolver(db, s, GTWC, NOW)
    people = [r.driver(pd(f, "Leclerc")) for f in ("Charles", "Arthur", "Lorenzo")]
    people += [r.driver(pd("Bobby", "Thompson")), r.driver(pd("Robert", "Thompson")), r.driver(pd("Parker", "Thompson"))]
    db.commit()
    assert len({p.id for p in people}) == 6


def test_fuzzy_similarity_never_merges_it_only_suggests(db, series):
    s = world(db, series)
    r = Resolver(db, s, GTWC, NOW)
    a, b = r.driver(pd("James", "Kell")), r.driver(pd("James", "Kellett"))
    c, d = r.driver(pd("Pieter", "Janssen")), Resolver(db, series["fia-wec"], WEC, NOW).driver(pd("Pieter", "Jansen"))
    db.commit()
    assert a.id != b.id and c.id != d.id
    report = build_report(db)
    pairs = {frozenset((x.a, x.b)) for x in report.driver_likely}
    assert frozenset(("James Kell", "James Kellett")) in pairs and frozenset(("Pieter Janssen", "Pieter Jansen")) in pairs
    assert db.scalar(select(func.count(Driver.id))) == 4  # reading the report changed nothing


def test_accent_and_case_only_differences_share_a_slug_and_so_one_driver_with_both_spellings(db, series):
    s = world(db, series)
    r = Resolver(db, s, WEC, NOW)
    a = r.driver(pd("Sébastien", "Buemi"))
    b = r.driver(pd("Sebastien", "BUEMI"))
    assert a.id == b.id
    assert {x.source_value for x in db.scalars(select(DriverAlias).where(DriverAlias.driver_id == a.id))} == {"Sébastien Buemi", "Sebastien BUEMI"}


def test_source_external_id_wins_over_the_spelling(db, series):
    s = world(db, series, "formula-1")
    r = Resolver(db, s, "formula1", NOW)
    a = r.driver(pd("Kimi", "Antonelli", external_id="ANDANT01"))
    again = Resolver(db, s, "formula1", NOW).driver(pd("Andrea Kimi", "Antonelli", external_id="ANDANT01"))
    assert a.id == again.id  # the source's own id says it is the same person, whatever the name looks like


def test_drivers_in_the_same_car_are_never_suggested_as_duplicates(db, series):
    s = world(db, series)
    apply_parsed_entries(db, s, [entry("e1", "7", "T", [pd("Jan", "Smit"), pd("Jan", "Smith")])], source_name="GTWC (entry list)", now=NOW, source_id=GTWC)
    db.commit()
    assert build_report(db).driver_likely == []  # two people share a car: by definition not the same person


# ---------------------------------------------------------------------------------------------- applying to stored data

def test_curated_aliases_merge_existing_duplicates_and_repoint_entries(db, series):
    s = world(db, series)
    # data imported before identity existed: both spellings are separate drivers on separate entries
    a, b = Driver(slug="dani-juncadella", first_name="Dani", last_name="Juncadella"), Driver(slug="daniel-juncadella", first_name="Daniel", last_name="Juncadella")
    db.add_all([a, b])
    db.flush()
    team = Team(series_id=s.id, slug="t", name="T")
    db.add(team)
    db.flush()
    season = db.scalar(select(Season))
    e1 = VehicleEntry(team_id=team.id, season_id=season.id, race_number="3")
    e2 = VehicleEntry(team_id=team.id, season_id=season.id, race_number="4")
    db.add_all([e1, e2])
    db.flush()
    from app.models import VehicleEntryDriver
    db.add_all([VehicleEntryDriver(vehicle_entry_id=e1.id, driver_id=a.id), VehicleEntryDriver(vehicle_entry_id=e2.id, driver_id=b.id)])
    db.commit()

    changes = apply_curated(db)
    db.commit()
    assert changes.merged_drivers == ["Dani Juncadella -> Daniel Juncadella"]
    assert db.scalar(select(func.count(Driver.id))) == 1
    keep = db.scalar(select(Driver))
    assert keep.slug == "daniel-juncadella"
    assert {lk.vehicle_entry_id for lk in db.scalars(select(VehicleEntryDriver))} == {e1.id, e2.id}
    assert apply_curated(db).merged_drivers == []  # idempotent


def test_curated_team_alias_merges_the_variant_into_the_canonical_team(db, series):
    s = world(db, series)
    season = db.scalar(select(Season))
    canon, var = Team(series_id=s.id, slug="getspeed-team-bartone-bros", name="GetSpeed Team Bartone Bros"), Team(series_id=s.id, slug="getspeed-team-bartonebros", name="GetSpeed Team BartoneBros")
    db.add_all([canon, var])
    db.flush()
    db.add(VehicleEntry(team_id=var.id, season_id=season.id, race_number="1"))
    db.commit()
    assert apply_curated(db).merged_teams == ["gt-world-challenge-europe: GetSpeed Team BartoneBros -> GetSpeed Team Bartone Bros"]
    db.commit()
    assert [t.slug for t in db.scalars(select(Team))] == ["getspeed-team-bartone-bros"]
    assert db.scalar(select(func.count(VehicleEntry.id)).where(VehicleEntry.team_id == canon.id)) == 1
    assert db.scalar(select(TeamAlias.source_value).where(TeamAlias.team_id == canon.id, TeamAlias.source_name == GTWC)) is not None


def test_sync_through_the_engine_keeps_provenance_and_uses_canonical_entities(db, series):
    s = world(db, series)
    apply_parsed_entries(db, s, [entry("e1", "3", "Mercedes - AMG Team Verstappen Racing", [pd("Dani", "Juncadella")], make="Mercedes-AMG", model="GT3 EVO")],
                         source_name="GTWC (entry list)", now=NOW, source_id=GTWC)
    apply_parsed_entries(db, s, [entry("e2", "3", "Mercedes - AMG Team Verstappen Racing", [pd("Daniel", "Juncadella")], make="Mercedes-AMG", model="GT3 EVO")],
                         source_name="GTWC (entry list)", now=NOW, source_id=GTWC)
    db.commit()
    assert db.scalar(select(func.count(Driver.id))) == 1 and db.scalar(select(func.count(Team.id))) == 1
    texts = {(e.manufacturer, e.model) for e in db.scalars(select(VehicleEntry))}
    assert texts == {("Mercedes-AMG", "GT3 EVO")}  # the entry rows keep the source's own spelling
    assert db.scalar(select(func.count(Manufacturer.id))) == 1 and db.scalar(select(func.count(VehicleModel.id))) == 1


def test_manufacturer_and_model_are_distinct_entities(db, series):
    s = world(db, series, "fia-wec", events=("e1",))
    apply_parsed_entries(db, s, [entry("e1", "50", "Ferrari AF Corse", [pd("A", "One")], make="Ferrari", model="499P"),
                                 entry("e1", "21", "Vista AF Corse", [pd("B", "Two")], make="Ferrari", model="296 LMGT3 Evo")],
                         source_name="WEC (entry list)", now=NOW, source_id=WEC)
    db.commit()
    ferrari = db.scalar(select(Manufacturer))
    assert ferrari.canonical_name == "Ferrari"
    assert sorted(m.canonical_name for m in ferrari.models) == ["296 LMGT3 Evo", "499P"]
    # same make in two entries -> one Manufacturer; models are unique per manufacturer
    assert db.scalar(select(func.count(Manufacturer.id))) == 1


def test_model_spelling_variants_with_only_punctuation_differences_are_one_model(db, series):
    s = world(db, series, "fia-wec", events=("e1",))
    r = Resolver(db, s, WEC, NOW)
    make = r.manufacturer("Toyota")
    a, b = r.vehicle_model(make, "GR010 - Hybrid"), r.vehicle_model(make, "GR010 Hybrid")
    c, d = r.vehicle_model(make, "911 GT3 R EVO"), r.vehicle_model(make, "911 GT3 R (992) EVO")
    assert a.id == b.id          # punctuation only
    assert c.id != d.id          # not guessed: two different strings stay two models
    assert r.vehicle_model(make, None) is None and r.vehicle_model(None, "X") is None


def test_backfill_creates_aliases_and_links_for_pre_identity_data_and_is_idempotent(db, series):
    s = world(db, series)
    season = db.scalar(select(Season))
    team = Team(series_id=s.id, slug="af-corse", name="AF Corse")
    drv = Driver(slug="a-b", first_name="A", last_name="B")
    db.add_all([team, drv])
    db.flush()
    e = VehicleEntry(team_id=team.id, season_id=season.id, race_number="1", manufacturer="Ferrari", model="296 GT3 EVO")
    db.add(e)
    db.flush()
    from app.models import VehicleEntryDriver
    db.add(VehicleEntryDriver(vehicle_entry_id=e.id, driver_id=drv.id))
    db.commit()
    first = backfill(db, NOW)
    db.commit()
    assert first.entries_linked == 1 and e.manufacturer_ref.canonical_name == "Ferrari" and e.vehicle_model.canonical_name == "296 GT3 EVO"
    assert db.scalar(select(DriverAlias.source_name)) == GTWC and db.scalar(select(TeamAlias.source_name)) == GTWC
    assert backfill(db, NOW).entries_linked == 0 and ensure_identity(db).aliases_added == 0


def test_every_curated_alias_has_a_reason_and_names_a_source():
    for a in DRIVER_ALIASES:
        assert a.reason and a.sources and a.variant != a.canonical
    for aliases in TEAM_ALIASES.values():
        assert all(a.reason and a.sources for a in aliases)


# ---------------------------------------------------------------------------------------------- the report

def test_identity_report_lists_canonicals_aliases_and_unresolved_names_without_merging(db, series):
    s = world(db, series)
    r = Resolver(db, s, GTWC, NOW)
    r.driver(pd("Dani", "Juncadella"))
    r.driver(pd("Daniel", "Juncadella"))
    r.driver(pd("Pieter", "Janssen"))
    r.driver(pd("Pieter", "Jansen"))
    r.team("Walkenhorst Motorsport")
    r.team("Walkenhorst Motorsports")
    r.manufacturer("Mercedes-AMG")
    r.manufacturer("Mercedes")
    db.commit()
    text = format_report(build_report(db))
    assert "Daniel Juncadella  <-  'Dani Juncadella'  [gt_world_challenge]" in text
    assert "Potential driver duplicates" in text and "Pieter Janssen" in text and "Pieter Jansen" in text
    assert "Walkenhorst Motorsport  |  Walkenhorst Motorsports" in text
    assert "Mercedes  |  Mercedes-AMG" in text or "Mercedes-AMG  |  Mercedes" in text
    assert db.scalar(select(func.count(Driver.id))) == 3  # nothing was merged by building the report


def test_transliteration_and_honorific_variants_map_through_explicit_gtwc_aliases(db, series):
    s = world(db, series)
    r = Resolver(db, s, GTWC, NOW)
    assert r.driver(pd("Marco", "Sorensen")).canonical_name == "Marco Sørensen"
    assert r.driver(pd("H.H.Prince", "Jefri Ibrahim")).canonical_name == "Prince Jefri Ibrahim"
    # James Kell / James Kellett stay separate: different teams, no identifier, no alias
    assert r.driver(pd("James", "Kell")).id != r.driver(pd("James", "Kellett")).id
