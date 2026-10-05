"""Logo registry coverage report (pure logic + the shipped registry; no database needed)."""

from pathlib import Path

from app.media_coverage import DEFAULT_MANIFEST, TeamRow, compute, format_report, load_registry, missing_files

LOGO = {"logo": {"src": "/assets/logos/x.svg"}}
REGISTRY = {
    "teams": {"team-wrt": LOGO, "ghost-team": LOGO},
    "manufacturers": {"bmw": LOGO, "mercedes": {**LOGO, "aliases": ["mercedes-benz"]}, "audi": {"logo": None}},
}


def row(series, slug, *makes, live=True):
    return TeamRow(series, slug, series.lower(), slug.title(), frozenset(makes), live)


def test_team_logo_beats_manufacturer_beats_text():
    rep = compute([
        row("GTWC", "team-wrt", "BMW"),               # own logo
        row("GTWC", "kessel", "BMW"),                  # manufacturer stands in
        row("GTWC", "unknown", "Corvette"),            # nothing in the registry
        row("GTWC", "mixed", "BMW", "Mercedes"),       # several makes: never a manufacturer identity
        row("GTWC", "no-cars"),                        # no entries at all
        row("GTWC", "audi-team", "Audi"),              # registry knows Audi but has no file for it
    ], REGISTRY)["GTWC"]
    assert (rep.teams, rep.team_logos) == (6, 1)
    assert rep.manufacturer_fallback == ["kessel"]
    assert sorted(rep.text_fallback) == ["audi-team", "mixed", "no-cars", "unknown"]
    assert rep.manufacturers_missing == {"corvette", "audi"}
    assert round(rep.coverage) == 17 and round(rep.identity_coverage) == 33


def test_manufacturer_aliases_and_slug_normalisation():
    rep = compute([row("WEC", "t", "Mercedes-Benz")], REGISTRY)["WEC"]
    assert rep.manufacturer_fallback == ["t"]


def test_series_are_reported_separately_and_flag_seed_data():
    reports = compute([row("F1", "a", live=False), row("WEC", "b")], REGISTRY)
    assert set(reports) == {"F1", "WEC"} and not reports["F1"].live and reports["WEC"].live
    out = format_report(reports, REGISTRY, orphans=["ghost-team"], broken=[])
    assert "F1:   (dev seed" in out and "Missing actual team logos" in out and "- WEC/b" in out and "ghost-team" in out


def test_many_teams_and_empty_database():
    reports = compute([row("GTWC", f"team-{i}", "BMW") for i in range(80)], REGISTRY)
    assert reports["GTWC"].teams == 80 and len(reports["GTWC"].manufacturer_fallback) == 80
    assert "TOTAL ACTUAL TEAM LOGO COVERAGE: 0/0 teams" in format_report({}, REGISTRY, [], [])


def test_shipped_registry_is_consistent():
    reg = load_registry(DEFAULT_MANIFEST)
    assert reg["version"] == 3
    assert missing_files(reg, DEFAULT_MANIFEST.parents[1] / "public") == []
    assert missing_files({"teams": {"x": {"logo": {"src": "/assets/logos/nope.svg"}}}, "manufacturers": {}}, Path("/nonexistent")) == ["/assets/logos/nope.svg"]


def test_a_team_logo_only_applies_to_the_series_it_is_for():
    """Team slugs are unique per series only: a same-named team in another championship must not inherit a logo."""
    reg = {"teams": {"af-corse": {**LOGO, "series": ["fia-wec"]}}, "manufacturers": {}}
    wec = TeamRow("WEC", "af-corse", "fia-wec", "AF Corse", frozenset(), True)
    other = TeamRow("XYZ", "af-corse", "some-other-series", "AF Corse", frozenset(), True)
    out = compute([wec, other], reg)
    assert out["WEC"].team_logos == 1 and out["XYZ"].team_logos == 0 and out["XYZ"].text_fallback == ["af-corse"]


def test_every_public_series_has_a_curated_hero_with_complete_provenance():
    from app.catalog import SERIES_CATALOG

    reg = load_registry(DEFAULT_MANIFEST)
    public_live = [s["slug"] for s in SERIES_CATALOG if s.get("public", True) and s["active"]]
    assert public_live and all(reg["series"][slug]["hero"] for slug in public_live)
    assert "imsa-weathertech" not in reg["series"]  # switched off: no card, no asset
    for slug in public_live:
        hero = reg["series"][slug]["hero"]
        for key in ("sourcePage", "originalUrl", "license", "author", "retrieved", "modifications", "alt"):
            assert hero[key], (slug, key)
        assert hero["src"].startswith("/assets/series/")


def test_actual_team_logo_coverage_for_the_shipped_registry_is_what_the_report_says():
    reg = load_registry(DEFAULT_MANIFEST)
    teams = [TeamRow("F1", s, "formula-1", s, frozenset(), True) for s in ("alpine", "audi", "ferrari", "red-bull-racing")]
    rep = compute(teams, reg)["F1"]
    assert (rep.team_logos, sorted(rep.text_fallback)) == (2, ["ferrari", "red-bull-racing"])
