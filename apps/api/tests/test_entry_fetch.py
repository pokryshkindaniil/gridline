"""Entry-list fetch logic over httpx.MockTransport serving the captured official pages."""

from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

import httpx
import pytest
from gridline_sources import EntryFetchPlan, get_source
from gridline_sources.base import SourceError
from gridline_sources.fia_wec.entries import parse_grid_page

GT_DIR = Path(get_source("gt_world_challenge").entries_dir)
GT_CAL = Path(get_source("gt_world_challenge").fixture_dir) / "calendar.html"
WEC_DIR = Path(get_source("fia_wec").entries_dir)
LIVE = "application/vnd.live-component+html"


@pytest.fixture
def gtwc(monkeypatch):
    src = get_source("gt_world_challenge")
    monkeypatch.setattr(src, "request_delay", 0)
    return src


@pytest.fixture
def wec(monkeypatch):
    src = get_source("fia_wec")
    monkeypatch.setattr(src, "request_delay", 0)
    return src


def gtwc_handler(fail: set[str] = frozenset(), seen: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if seen is not None:
            seen.append(path)
        if path == "/entry-lists":
            return httpx.Response(200, text=(GT_DIR / "entry-lists.html").read_text())
        if path == "/calendar":
            return httpx.Response(200, text=GT_CAL.read_text())
        slug = urllib.parse.unquote(path.rsplit("/", 1)[1])
        if slug in fail:
            return httpx.Response(503)
        return httpx.Response(200, text=(GT_DIR / f"entry_{urllib.parse.quote(slug, safe='')}.html").read_text())
    return handler


def wec_handler(*, fail_race: set[str] = frozenset(), fail_driver: set[str] = frozenset(), calls: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        path, q = request.url.path, dict(request.url.params)
        if calls is not None:
            calls.append((request.method, path, request))
        if path == "/en/page/grid":
            return httpx.Response(200, text=(WEC_DIR / "grid_page.html").read_text())
        if request.method == "POST" and path.endswith("/changeRace"):
            payload = json.loads(urllib.parse.parse_qs(request.content.decode())["data"][0])
            rid = str(payload["updated"]["raceId"])
            if rid in fail_race:
                return httpx.Response(500, text="boom")
            return httpx.Response(200, text=(WEC_DIR / f"grid_race{rid}.html").read_text(), headers={"content-type": LIVE})
        if path.startswith("/en/car/"):
            _, _, _, year, num = path.split("/")
            return httpx.Response(200, text=(WEC_DIR / f"car_{year}_{num}_race{q['race']}.html").read_text())
        if path.startswith("/en/driver/"):
            did = path.rsplit("/", 1)[1]
            if did in fail_driver:
                return httpx.Response(503)
            return httpx.Response(200, text=(WEC_DIR / f"driver_2026_{did}.html").read_text())
        return httpx.Response(404)
    return handler


# ------------------------------------------------------------------------------------------ GTWC

async def test_gtwc_fetch_walks_index_calendar_and_each_published_list(gtwc, monkeypatch):
    monkeypatch.setattr(gtwc, "transport", httpx.MockTransport(gtwc_handler()))
    raw = await gtwc.fetch_entries(EntryFetchPlan())
    res = gtwc.parse_entries(raw)
    assert res.issues == [] and len(res.entries) == 449 and raw.fetch_errors == {}
    assert len(res.events_parsed) == 9


async def test_gtwc_settled_events_are_not_requested(gtwc, monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(gtwc, "transport", httpx.MockTransport(gtwc_handler(seen=seen)))
    raw = await gtwc.fetch_entries(EntryFetchPlan(settled_events=frozenset({"e246", "e247"})))
    assert "/entry-list/2026/circuit-paul-ricard" not in seen and "/entry-list/2026/brands-hatch" not in seen
    res = gtwc.parse_entries(raw)
    assert res.issues == [] and "e246" not in res.events_parsed and len(res.events_parsed) == 7


async def test_gtwc_a_503_on_one_list_quarantines_only_that_event(gtwc, monkeypatch):
    monkeypatch.setattr(gtwc, "transport", httpx.MockTransport(gtwc_handler(fail={"monza"})))
    raw = await gtwc.fetch_entries(EntryFetchPlan())
    res = gtwc.parse_entries(raw)
    assert [i.event for i in res.issues] == ["monza"] and "503" in res.issues[0].message
    assert len(res.events_parsed) == 8


async def test_gtwc_index_failure_fails_the_whole_fetch(gtwc, monkeypatch):
    monkeypatch.setattr(gtwc, "transport", httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(SourceError):
        await gtwc.fetch_entries(EntryFetchPlan())


# ------------------------------------------------------------------------------------------ WEC

async def test_wec_fetch_uses_the_grids_own_race_call_then_car_and_driver_pages(wec, monkeypatch):
    calls: list = []
    monkeypatch.setattr(wec, "transport", httpx.MockTransport(wec_handler(calls=calls)))
    raw = await wec.fetch_entries(EntryFetchPlan())
    res = wec.parse_entries(raw)
    assert res.issues == [] and len(res.entries) == 105 and len(res.events_parsed) == 3
    posts = [r for m, _p, r in calls if m == "POST"]
    assert len(posts) == 3
    assert posts[0].headers["accept"] == LIVE and posts[0].headers["x-requested-with"] == "XMLHttpRequest"
    sent = json.loads(urllib.parse.parse_qs(posts[0].content.decode())["data"][0])
    assert sent["props"]["seasonId"] == "4175" and isinstance(sent["updated"]["raceId"], int)  # props as the page gave them
    drivers = [p for m, p, _r in calls if p.startswith("/en/driver/")]
    assert len(drivers) == len(set(drivers))  # each profile is fetched once, however many races it appears in


async def test_wec_settled_race_is_not_fetched(wec, monkeypatch):
    calls: list = []
    monkeypatch.setattr(wec, "transport", httpx.MockTransport(wec_handler(calls=calls)))
    raw = await wec.fetch_entries(EntryFetchPlan(settled_events=frozenset({"official-prologue-imola-2026"})))
    res = wec.parse_entries(raw)
    assert res.issues == [] and len(res.events_parsed) == 2
    assert not any(q == "5042" for _m, _p, r in calls if (q := r.url.params.get("race")))


async def test_wec_race_grid_call_failing_quarantines_that_race(wec, monkeypatch):
    race = next(i for i, n in parse_grid_page((WEC_DIR / "grid_page.html").read_text()).races if "SPA" in n)
    monkeypatch.setattr(wec, "transport", httpx.MockTransport(wec_handler(fail_race={race})))
    raw = await wec.fetch_entries(EntryFetchPlan())
    res = wec.parse_entries(raw)
    assert [i.event for i in res.issues] == ["totalenergies-6-hours-of-spa-francorchamps-2026"]
    assert "HTTP 500" in res.issues[0].message and len(res.events_parsed) == 2


async def test_wec_driver_profile_failing_quarantines_the_races_that_need_it(wec, monkeypatch):
    monkeypatch.setattr(wec, "transport", httpx.MockTransport(wec_handler(fail_driver={"9024"})))  # Félix da Costa, #35
    raw = await wec.fetch_entries(EntryFetchPlan())
    res = wec.parse_entries(raw)
    assert res.entries == [] and len(res.issues) == 3  # every fixture race has #35


async def test_wec_grid_page_failure_fails_the_whole_fetch(wec, monkeypatch):
    monkeypatch.setattr(wec, "transport", httpx.MockTransport(lambda r: httpx.Response(502)))
    with pytest.raises(SourceError):
        await wec.fetch_entries(EntryFetchPlan())


async def test_wec_grid_page_without_the_component_fails_loudly(wec, monkeypatch):
    monkeypatch.setattr(wec, "transport", httpx.MockTransport(lambda r: httpx.Response(200, text="<html>redesign</html>")))
    with pytest.raises(SourceError, match="markup changed"):
        await wec.fetch_entries(EntryFetchPlan())
