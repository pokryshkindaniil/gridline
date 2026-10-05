"""F1 and WEC fetch logic exercised over httpx.MockTransport serving the captured fixtures."""

import re
from pathlib import Path

import httpx
from gridline_sources import get_source


def f1_handler(request: httpx.Request) -> httpx.Response:
    fx = Path(get_source("formula1").fixture_dir)
    path = request.url.path
    if path == "/en/racing/2026":
        return httpx.Response(200, text=(fx / "index.html").read_text())
    slug = path.rsplit("/", 1)[1]
    return httpx.Response(200, text=(fx / f"race_{slug}.html").read_text())


def wec_handler(request: httpx.Request) -> httpx.Response:
    fx = Path(get_source("fia_wec").fixture_dir)
    path = request.url.path
    if path == "/en/season/2026":
        slugs = sorted({m.group(1) for p in fx.glob("race_*.html") if (m := re.match(r"race_(.+)\.html", p.name))})
        return httpx.Response(200, text="".join(f'<a href="/en/race/{s}">x</a>' for s in slugs))
    if path.startswith("/en/race/calendar/"):
        # map calendar id -> ics fixture via the html link
        cid = path.rsplit("/", 1)[1]
        for html in fx.glob("race_*.html"):
            if f"/en/race/calendar/{cid}" in html.read_text():
                return httpx.Response(200, text=html.with_suffix(".ics").read_text(), headers={"content-type": "text/calendar"})
        return httpx.Response(404)
    slug = path.rsplit("/", 1)[1]
    return httpx.Response(200, text=(fx / f"race_{slug}.html").read_text())


async def test_f1_fetch_walks_index_then_race_pages():
    src = get_source("formula1")
    src.year, src.transport, src.request_delay = 2026, httpx.MockTransport(f1_handler), 0
    result = src.parse(await src.fetch())
    assert result.issues == [] and len(result.sessions) == len(src.parse(src.load_fixture()).sessions)


async def test_f1_race_page_5xx_quarantines_that_race_only():
    def handler(request):
        if request.url.path.endswith("/japan"):
            return httpx.Response(503)
        return f1_handler(request)

    src = get_source("formula1")
    src.year, src.transport, src.request_delay = 2026, httpx.MockTransport(handler), 0
    result = src.parse(await src.fetch())
    assert [i.event for i in result.issues] == ["japan"] and "503" in result.issues[0].message
    assert not any(s.event_external_id == "japan" for s in result.sessions)


async def test_wec_fetch_follows_calendar_links_to_official_ics():
    src = get_source("fia_wec")
    src.year, src.transport, src.request_delay = 2026, httpx.MockTransport(wec_handler), 0
    result = src.parse(await src.fetch())
    assert result.issues == []
    assert len(result.sessions) == len(src.parse(src.load_fixture()).sessions) == 71
