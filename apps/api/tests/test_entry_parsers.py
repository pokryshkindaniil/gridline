"""Entry-list parsers against captured official pages (packages/sources/**/entry_fixtures), plus the name helpers."""

from __future__ import annotations

import re
from collections import Counter, defaultdict

import pytest
from gridline_sources import EntryFetchPlan, get_source, supports_entries
from gridline_sources.entries import (
    clean,
    is_placeholder,
    smart_title,
    split_caps_surname,
    split_make_model,
    surname_case,
)
from gridline_sources.fia_wec.entries import (
    parse_car_page,
    parse_driver_page,
    parse_grid_fragment,
    parse_grid_page,
    split_name,
)
from gridline_sources.gt_world_challenge.entries import calendar_event_ids, index_links, parse_entry_page


@pytest.fixture(scope="module")
def gtwc():
    src = get_source("gt_world_challenge")
    raw = src.load_entries_fixture()
    return src, raw, src.parse_entries(raw)


@pytest.fixture(scope="module")
def wec():
    src = get_source("fia_wec")
    raw = src.load_entries_fixture()
    return src, raw, src.parse_entries(raw)


def by_event(entries):
    out = defaultdict(list)
    for e in entries:
        out[e.event_external_id].append(e)
    return out


# ------------------------------------------------------------------------------------------ helpers

def test_capabilities_are_per_adapter():
    assert supports_entries(get_source("gt_world_challenge"))
    assert supports_entries(get_source("fia_wec"))
    assert supports_entries(get_source("formula1"))  # season-wide roster
    assert not supports_entries(get_source("imsa"))  # fixture-only
    assert not supports_entries(get_source("imsa"))


@pytest.mark.parametrize("raw,expected", [
    ("Dorian BOCCOLACCI", ("Dorian", "Boccolacci")),
    ("Kelvin VAN DER LINDE", ("Kelvin", "Van der Linde")),
    ("Pierre Louis CHOVET", ("Pierre Louis", "Chovet")),
    ("Jean-Karl VERNAY", ("Jean-Karl", "Vernay")),
    ("Sven MÜLLER", ("Sven", "Müller")),
    ("Kobe PAUWELS ", ("Kobe", "Pauwels")),
])
def test_gtwc_names_split_on_the_capitalised_surname(raw, expected):
    assert split_caps_surname(raw) == expected


@pytest.mark.parametrize("raw", ["Dorian Boccolacci", "BOCCOLACCI", "TBA", ""])
def test_names_without_a_capitalised_surname_are_not_guessed(raw):
    assert split_caps_surname(raw) is None


def test_placeholders_are_unannounced_slots_not_drivers():
    assert all(is_placeholder(x) for x in ("TBA", "tbc", "/", " ", "-"))
    assert not is_placeholder("Max HESSE")


def test_wec_names_need_both_pages_to_agree():
    assert split_name("Félix da Costa António", "António Félix da Costa") == ("António", "Félix da Costa")
    assert split_name("Nato Norman", "Norman Nato") == ("Norman", "Nato")
    assert split_name("MAGNUSSEN Kevin", "Kevin Magnussen") == ("Kevin", "Magnussen")
    with pytest.raises(Exception, match="cannot split"):
        split_name("Nato Norman", "Somebody Else")


def test_display_case_helpers():
    assert smart_title("BMW M TEAM WRT") == "BMW M Team WRT"
    assert smart_title("RACING SPIRIT OF LEMAN") == "Racing Spirit of Leman"
    assert smart_title("PEUGEOT TOTALENERGIES") == "Peugeot TotalEnergies"
    assert smart_title("Iron Lynx") == "Iron Lynx"  # mixed case is already display case
    assert surname_case("VAN DER LINDE") == "Van der Linde"
    assert split_make_model("Mercedes-AMG GT3 EVO") == ("Mercedes-AMG", "GT3 EVO")
    assert split_make_model("Mystery GT3") == (None, "Mystery GT3")
    assert clean("  a\xa0 b ") == "a b"


# ------------------------------------------------------------------------------------------ GTWC

def test_gtwc_fixture_covers_every_published_event_without_issues(gtwc):
    _src, raw, res = gtwc
    published = index_links(raw.documents["entry-lists.html"])
    assert len(published) == 9 and res.issues == []
    assert res.events_parsed == {"e246", "e247", "e248", "e249", "e250", "e251", "e252", "e253", "e254"}
    assert len(res.entries) == 449
    assert set(calendar_event_ids(raw.documents["calendar.html"]).values()) >= res.events_parsed


def test_gtwc_sprint_cup_lists_have_two_drivers_and_endurance_three_or_four(gtwc):
    events = by_event(gtwc[2].entries)
    barcelona, paul_ricard, spa = events["e254"], events["e246"], events["e249"]
    assert {e.competition for e in barcelona} == {"Sprint Cup"}
    assert Counter(len(e.drivers) for e in barcelona) == {2: len(barcelona)}
    assert {e.competition for e in paul_ricard} == {"Endurance Cup"}
    assert max(len(e.drivers) for e in paul_ricard) == 3
    assert {len(e.drivers) for e in spa} == {3, 4}


def test_gtwc_same_car_has_a_different_crew_at_different_events(gtwc):
    events = by_event(gtwc[2].entries)

    def crew(event, number):
        e = next(x for x in events[event] if x.race_number == number)
        return [d.slug for d in e.drivers]

    barcelona, brands, magny = crew("e254", "2"), crew("e247", "2"), crew("e251", "2")
    assert barcelona == ["sven-muller", "dorian-boccolacci"]
    assert brands == ["dorian-boccolacci", "morris-schuring"]
    assert magny == ["alessio-picariello", "dorian-boccolacci"]


def test_gtwc_class_is_event_specific_too(gtwc):
    events = by_event(gtwc[2].entries)
    cls = lambda ev: next(e.class_name for e in events[ev] if e.team_name == "AF Corse" and e.race_number == "51")  # noqa: E731
    assert cls("e254") == "Gold" and cls("e246") == "Pro"  # Sprint vs Endurance grading


def test_gtwc_entry_fields(gtwc):
    e = next(x for x in by_event(gtwc[2].entries)["e254"] if x.race_number == "2")
    assert (e.team_name, e.manufacturer, e.model, e.class_name, e.competition) == (
        "Boutsen VDS", "Porsche", "911 GT3 R (992) EVO", "Pro", "Sprint Cup")
    assert e.drivers[0].nationality_code == "DE" and e.drivers[1].nationality_code == "FR"
    assert e.source_url == "https://www.gt-world-challenge-europe.com/entry-list/2026/barcelona"


def test_gtwc_unannounced_drivers_keep_the_car_but_not_a_made_up_driver(gtwc):
    events = by_event(gtwc[2].entries)
    tba = next(e for e in events["e251"] if e.race_number == "914")
    assert tba.drivers == ()  # all slots TBA
    assert len(next(e for e in events["e248"] if e.race_number == "99").drivers) == 2  # third slot TBA


def test_gtwc_a_broken_event_is_quarantined_and_the_rest_still_parse(gtwc):
    src, raw, _ = gtwc
    docs = dict(raw.documents)
    docs["entry_misano.html"] = "<html><title>Misano Entry List 2026</title><main><p>redesigned</p></main></html>"
    docs["entry_monza.html"] = docs["entry_monza.html"].replace("<td>3</td>", "<td>2</td>", 1)  # duplicate number
    res = src.parse_entries(type(raw)(raw.source_url, raw.fetched_at, docs, fetch_errors={"zandvoort": "HTTP 503"}))
    bad = {i.event for i in res.issues}
    assert bad == {"misano", "monza", "zandvoort"}
    assert res.events_parsed == {"e246", "e247", "e249", "e251", "e252", "e254"}
    assert {e.event_external_id for e in res.entries}.isdisjoint({"e250", "e248", "e253"})


def test_gtwc_unreadable_driver_name_quarantines_the_event_not_a_guess(gtwc):
    _src, raw, _ = gtwc
    doc = raw.documents["entry_barcelona.html"].replace("Sven MÜLLER", "Sven Müller")
    with pytest.raises(Exception, match="cannot split driver name"):
        parse_entry_page(doc, "e254", "u")


def test_gtwc_unpublished_lists_are_not_an_error():
    src = get_source("gt_world_challenge")
    raw = src.load_entries_fixture()
    docs = {"entry-lists.html": re.sub(r'<a class="entry-lists__link-button.*?</a>', '<span class="no-link">Not available</span>',
                                       raw.documents["entry-lists.html"], flags=re.S),
            "calendar.html": raw.documents["calendar.html"]}
    res = src.parse_entries(type(raw)(raw.source_url, raw.fetched_at, docs))
    assert res.entries == [] and res.issues == []


# ------------------------------------------------------------------------------------------ WEC

def test_wec_fixture_events_and_multicar_teams(wec):
    _src, _raw, res = wec
    assert res.issues == []
    assert res.events_parsed == {"official-prologue-imola-2026", "totalenergies-6-hours-of-spa-francorchamps-2026",
                                 "lone-star-le-mans-2026"}
    spa = {e.race_number: e for e in by_event(res.entries)["totalenergies-6-hours-of-spa-francorchamps-2026"]}
    assert len(spa) == 35
    # two cars, same team (#50/#51), three drivers each, published order kept
    assert spa["50"].team_name == spa["51"].team_name == "Ferrari AF Corse"
    assert [d.slug for d in spa["50"].drivers] == ["antonio-fuoco", "miguel-molina", "nicklas-nielsen"]
    assert (spa["51"].manufacturer, spa["51"].model, spa["51"].class_name) == ("Ferrari", "499P", "Hypercar")
    # a customer team running the same Ferrari under another name is a different team
    assert spa["83"].team_name == "AF Corse"
    assert spa["21"].class_name == "LMGT3" and spa["21"].model == "296 LMGT3 Evo"
    assert Counter(len(e.drivers) for e in spa.values()) == {3: 33, 2: 2}  # two cars race with a two-man crew


def test_wec_event_specific_replacements(wec):
    events = by_event(wec[2].entries)

    def crew(event):
        return [d.slug for d in next(e for e in events[event] if e.race_number == "12").drivers]

    assert crew("official-prologue-imola-2026") == ["alex-lynn", "will-stevens", "norman-nato"]
    assert crew("totalenergies-6-hours-of-spa-francorchamps-2026") == ["will-stevens", "norman-nato", "louis-deletraz"]
    assert crew("lone-star-le-mans-2026") == ["will-stevens", "norman-nato", "ricky-taylor"]


def test_wec_entry_fields_and_provenance(wec):
    e = next(x for x in by_event(wec[2].entries)["lone-star-le-mans-2026"] if x.race_number == "007")
    assert e.race_number == "007" and e.manufacturer == "Aston Martin" and e.model == "Valkyrie"
    assert e.team_name == "Aston Martin Thor Team" and e.class_name == "Hypercar"
    assert e.source_url.startswith("https://www.fiawec.com/en/car/2026/007?race=")
    assert all(d.nationality_code for d in e.drivers)


def test_wec_pages_parse_in_isolation(wec):
    _src, raw, _ = wec
    grid = parse_grid_page(raw.documents["grid_page.html"])
    assert grid.year == 2026 and len(grid.races) == 3
    assert grid.event_external_id("ROLEX 6 HOURS OF SÃO PAULO") == "rolex-6-hours-of-sao-paulo-2026"
    rid = grid.races[1][0]
    nums = parse_grid_fragment(raw.documents[f"grid_race{rid}.html"])
    assert len(nums) == len(set(nums)) == 35
    car = parse_car_page(raw.documents[f"car_2026_50_race{rid}.html"])
    assert (car.team, car.category, car.car) == ("FERRARI AF CORSE", "Hypercar", "FERRARI - 499P")
    prof = parse_driver_page(raw.documents["driver_2026_9024.html"])
    # the heading marks the first name; the nationality comes from the 'Nationality' row, not a race-calendar flag
    assert (prof.first_name, prof.last_name, prof.nationality_code) == ("António", "Félix da Costa", "PT")


def test_wec_event_with_missing_pages_is_quarantined_others_survive(wec):
    src, raw, _ = wec
    spa_id = next(i for i, n in parse_grid_page(raw.documents["grid_page.html"]).races if "SPA" in n)
    docs = {k: v for k, v in raw.documents.items() if k != f"car_2026_50_race{spa_id}.html"}
    res = src.parse_entries(type(raw)(raw.source_url, raw.fetched_at, docs))
    assert [i.event for i in res.issues] == ["totalenergies-6-hours-of-spa-francorchamps-2026"]
    assert len(res.events_parsed) == 2


def test_wec_names_that_do_not_agree_quarantine_only_that_event(wec):
    src, raw, _ = wec
    docs = dict(raw.documents)
    docs["driver_2026_9024.html"] = docs["driver_2026_9024.html"].replace("António Félix da Costa", "Someone Different")
    res = src.parse_entries(type(raw)(raw.source_url, raw.fetched_at, docs))
    assert res.issues and all("cannot split driver name" in i.message for i in res.issues)
    assert not any(d.slug == "someone-different" for e in res.entries for d in e.drivers)


def test_wec_race_with_a_fetch_error_is_reported(wec):
    src, raw, _ = wec
    res = src.parse_entries(type(raw)(raw.source_url, raw.fetched_at, raw.documents,
                                      fetch_errors={"lone-star-le-mans-2026": "HTTP 503"}))
    assert [(i.event, i.message) for i in res.issues] == [("lone-star-le-mans-2026", "HTTP 503")]
    assert "lone-star-le-mans-2026" not in res.events_parsed


def test_wec_grid_markup_change_fails_loudly(wec):
    src, raw, _ = wec
    docs = dict(raw.documents, **{"grid_page.html": "<html><body>new site</body></html>"})
    with pytest.raises(Exception, match="markup changed"):
        src.parse_entries(type(raw)(raw.source_url, raw.fetched_at, docs))


def test_fetch_plan_defaults_to_nothing_settled():
    assert EntryFetchPlan().settled_events == frozenset()
