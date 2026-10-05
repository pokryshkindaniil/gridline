"""Series switched off (IMSA): kept in code and data, absent from every public surface, impossible to select in a feed."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.catalog import SERIES_CATALOG, ensure_series
from app.models import CalendarFeed, Series
from app.services.feeds import FeedError, resolve_series
from app.services.queries import sessions_stmt
from app.services.series_visibility import public_series_slugs

IMSA = "imsa-weathertech"


def test_visibility_is_explicit_on_every_catalogue_entry_and_independent_of_active():
    assert all(isinstance(s.get("public"), bool) and isinstance(s["active"], bool) for s in SERIES_CATALOG)
    assert {s["slug"]: (s["active"], s["public"]) for s in SERIES_CATALOG} == {
        "formula-1": (True, True), "fia-wec": (True, True), "gt-world-challenge-europe": (True, True),
        "imsa-weathertech": (True, False),   # has an adapter, but hidden
        "wrc": (False, False), "formula-e": (False, False), "motogp": (False, False),
    }


def test_only_f1_wec_and_gtwc_are_public_and_unsupported_series_stay_stored_but_hidden(db, client):
    ensure_series(db)
    db.commit()
    assert public_series_slugs(db) == {"formula-1", "fia-wec", "gt-world-challenge-europe"}
    assert {s.slug for s in db.scalars(select(Series))} == {s["slug"] for s in SERIES_CATALOG}  # nothing deleted
    assert {s["slug"] for s in client.get("/series").json()} == {"formula-1", "fia-wec", "gt-world-challenge-europe"}
    for hidden in ("imsa-weathertech", "wrc", "formula-e", "motogp"):
        assert client.get(f"/series/{hidden}").status_code == 404


def test_repeated_ensure_series_never_resets_unsupported_series_to_public(db):
    for _ in range(3):
        ensure_series(db)
        db.commit()
    for s in db.scalars(select(Series).where(Series.slug.in_(["wrc", "formula-e", "motogp", IMSA]))):
        s.public = True   # a wrong value (as on the production database before 0008) …
    db.commit()
    ensure_series(db)
    db.commit()           # … is corrected again by the catalogue
    assert public_series_slugs(db) == {"formula-1", "fia-wec", "gt-world-challenge-europe"}


def test_ensure_series_asserts_the_flag_every_time(db):
    ensure_series(db)
    imsa = db.scalar(select(Series).where(Series.slug == IMSA))
    imsa.public = True  # somebody flipped it by hand
    db.commit()
    ensure_series(db)
    db.commit()
    assert db.scalar(select(Series.public).where(Series.slug == IMSA)) is False
    assert IMSA not in public_series_slugs(db)


def test_imsa_is_hidden_from_the_public_series_listing_and_detail(client, seeded):
    slugs = {s["slug"] for s in client.get("/series").json()}
    assert IMSA not in slugs and {"formula-1", "fia-wec", "gt-world-challenge-europe"} <= slugs
    assert client.get(f"/series/{IMSA}").status_code == 404
    assert client.get(f"/series/{IMSA}/events").status_code == 404
    assert client.get(f"/series/{IMSA}/teams").status_code == 404
    assert client.get(f"/series/{IMSA}/entry-events").status_code == 404


def test_imsa_events_and_sessions_are_absent_from_every_public_listing(client, seeded):
    assert all(e["series_slug"] != IMSA for e in client.get("/events", params={"limit": 500}).json())
    assert client.get("/sessions", params={"series": IMSA}).json() == []
    assert all(s["series"]["slug"] != IMSA for s in client.get("/sessions", params={"limit": 2000}).json())
    w = client.get("/weekend", params={"at": "2026-10-04T10:00:00Z", "tz": "Europe/Madrid"}).json()
    assert IMSA not in {s["series"]["slug"] for s in w["sessions"]}
    assert client.get("/sources/health").json() and IMSA not in {h["series"] for h in client.get("/sources/health").json()}


def test_a_hidden_series_event_is_not_reachable_by_id(client, seeded, db):
    from app.models import Event, Season

    ev = db.scalar(select(Event).join(Season).join(Series).where(Series.slug == IMSA))
    assert ev is not None  # the fixture data is still there
    assert client.get(f"/events/{ev.id}").status_code == 404
    assert client.get(f"/events/{ev.id}/sessions").status_code == 404


def test_a_feed_cannot_be_created_with_a_disabled_series(client, seeded):
    r = client.post("/feeds", json={"series": [IMSA], "session_types": ["race"], "timezone": "UTC"})
    assert r.status_code == 422 and IMSA in r.json()["detail"]
    mixed = client.post("/feeds", json={"series": ["formula-1", IMSA], "session_types": ["race"], "timezone": "UTC"})
    assert mixed.status_code == 422  # one disabled series rejects the whole request: nothing is silently dropped


def test_a_feed_cannot_be_edited_to_include_a_disabled_series(client, seeded):
    made = client.post("/feeds", json={"series": ["formula-1"], "session_types": ["race"], "timezone": "UTC"}).json()
    r = client.patch(f"/feeds/{made['public_token']}", json={"series": [IMSA]}, headers={"X-Edit-Token": made["edit_token"]})
    assert r.status_code == 422
    assert [s["slug"] for s in client.get(f"/feeds/{made['public_token']}").json()["series"]] == ["formula-1"]


def test_a_series_switched_off_after_a_feed_selected_it_drops_out_of_that_feed(client, seeded, db):
    made = client.post("/feeds", json={"series": ["formula-1", "gt-world-challenge-europe"], "session_types": ["race"], "timezone": "UTC"}).json()
    token = made["public_token"]
    feed = db.scalar(select(CalendarFeed).where(CalendarFeed.public_token == token))
    imsa = db.scalar(select(Series).where(Series.slug == IMSA))
    imsa.public = True
    db.commit()
    feed.series.append(imsa)  # legacy row: the feed selected IMSA while it was public
    imsa.public = False
    db.commit()
    ics = client.get(f"/calendar/{token}.ics").text
    assert "IMSA" not in ics and "BEGIN:VEVENT" in ics
    assert IMSA not in [s["slug"] for s in client.get(f"/feeds/{token}").json()["series"]]


def test_resolve_series_rejects_disabled_series_like_unknown_ones(db, series):
    assert [s.slug for s in resolve_series(db, ["formula-1"])] == ["formula-1"]
    with pytest.raises(FeedError, match="unknown series: imsa-weathertech"):
        resolve_series(db, [IMSA])


def test_internal_tooling_and_tests_can_still_reach_the_fixture_data(db, seeded):
    public = list(db.scalars(sessions_stmt()).unique())
    assert public and all(s.event.season.series.slug != IMSA for s in public)
    hidden = list(db.scalars(sessions_stmt(include_hidden=True).where(Series.slug == IMSA)).unique())
    assert hidden and all(s.event.season.series.public is False for s in hidden)


def test_the_imsa_adapter_and_fixtures_are_still_registered_but_fixture_only():
    from gridline_sources import get_source

    src = get_source("imsa")
    assert src.live is False and src.load_fixture().documents
