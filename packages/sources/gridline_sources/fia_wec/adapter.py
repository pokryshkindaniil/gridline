from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import httpx

from .. import base
from ..base import MotorsportSource, ParseResult, RawSchedule
from ..entries import EntryFetchPlan, EntryParseResult, RawEntries
from .entries import (
    GRID_PATH,
    car_key,
    driver_key,
    grid_key,
    parse_car_page,
    parse_entry_documents,
    parse_grid_fragment,
    parse_grid_page,
)
from .parser import parse_events

SITE = "https://www.fiawec.com"


class FiaWecSource(MotorsportSource):
    def __init__(self) -> None:
        self.year: int | None = None  # override for tests / backfills
        self.source_id = "fia_wec"
        self.series_slug = "fia-wec"
        self.source_name = "FIA WEC (fiawec.com)"
        self.official_url = f"{SITE}/en/season/{datetime.now(UTC).year}"
        self.fixture_dir = Path(__file__).parent / "fixtures"
        self.limitation = (
            "Uses each race page's official 'Add to my calendar' ICS (IANA TZID or UTC, stable session UIDs) and "
            "the page's JSON-LD for cancellations. UTC-only ICS files need the circuit in a maintained timezone "
            "map; unmapped events are quarantined, never defaulted to UTC."
        )
        self.entries_url = f"{SITE}{GRID_PATH}"
        self.entries_dir = Path(__file__).parent / "entry_fixtures"
        self.entries_limitation = (
            "Entries come from the official Grid page: the per-race grid (the page's own race selector), each car's "
            "technical sheet for that race and the driver profiles. A race appears only once WEC publishes its grid. "
            "The per-race grid is loaded through the site's internal live-component call; if that changes the sync "
            "fails and stored entries are kept. WEC publishes no per-driver session assignment."
        )

    async def fetch(self) -> RawSchedule:
        year = self.year or datetime.now(UTC).year
        season_url = f"{SITE}/en/season/{year}"
        docs: dict[str, str] = {}
        async with base.http_client(self.transport) as client:
            season = await base.http_get(client, season_url)
            slugs = sorted(set(re.findall(rf'href="/en/race/([a-z0-9-]+-{year})"', season)))
            if not slugs:
                raise base.SourceError(f"WEC season page {season_url} lists no races; markup changed?")
            for slug in slugs:
                try:
                    html = await base.http_get(client, f"{SITE}/en/race/{slug}")
                    docs[f"race_{slug}.html"] = html
                    cal = re.search(r'href="(/en/race/calendar/\d+)"', html)
                    if cal:
                        docs[f"race_{slug}.ics"] = await base.http_get(client, SITE + cal[1])
                except base.SourceError as exc:
                    docs[f"race_{slug}.html"] = f"<!-- FETCH-ERROR {exc} -->"
                await asyncio.sleep(self.request_delay)
        return RawSchedule(season_url, datetime.now(UTC), docs)

    def parse(self, raw: RawSchedule) -> ParseResult:
        return parse_events(raw)

    # ---- EntryListSource capability -------------------------------------------------------------
    async def fetch_entries(self, plan: EntryFetchPlan) -> RawEntries:
        docs: dict[str, str] = {}
        errors: dict[str, str] = {}
        async with base.http_client(self.transport) as client:

            async def get(url: str) -> str:
                text = await base.http_get(client, url)
                await asyncio.sleep(self.request_delay)
                return text

            docs["grid_page.html"] = grid_html = await get(self.entries_url)
            grid = parse_grid_page(grid_html)
            driver_errors: dict[str, str] = {}
            for race_id, race_name in grid.races:
                event_id = grid.event_external_id(race_name)
                if event_id in plan.settled_events:
                    continue
                try:
                    resp = await client.post(
                        SITE + grid.component_url + "/changeRace",
                        data={"data": json.dumps({"props": grid.props, "updated": {"raceId": int(race_id)}, "args": {}})},
                        headers={"Accept": "application/vnd.live-component+html", "X-Requested-With": "XMLHttpRequest",
                                 "X-Live-Url": GRID_PATH},
                    )
                    await asyncio.sleep(self.request_delay)
                    if resp.status_code != 200 or "vnd.live-component" not in resp.headers.get("content-type", ""):
                        raise base.SourceError(f"race grid call for {race_name!r} returned HTTP {resp.status_code}")
                    docs[grid_key(race_id)] = resp.text
                    for num in parse_grid_fragment(resp.text):
                        car_html = await get(f"{SITE}/en/car/{grid.year}/{num}?race={race_id}")
                        docs[car_key(grid.year, num, race_id)] = car_html
                        for did, _ in parse_car_page(car_html).drivers:
                            key = driver_key(grid.year, did)
                            if key in docs:
                                continue
                            if did in driver_errors:
                                raise base.SourceError(driver_errors[did])
                            try:
                                docs[key] = await get(f"{SITE}/en/driver/{grid.year}/{did}")
                            except base.SourceError as exc:
                                driver_errors[did] = str(exc)
                                raise
                except (base.SourceError, httpx.HTTPError) as exc:
                    docs.pop(grid_key(race_id), None)
                    errors[event_id] = str(exc)
        return RawEntries(self.entries_url, datetime.now(UTC), docs, fetch_errors=errors)

    def parse_entries(self, raw: RawEntries) -> EntryParseResult:
        return parse_entry_documents(raw)

    def load_entries_fixture(self) -> RawEntries:
        docs = {p.name: p.read_text(encoding="utf-8") for p in sorted(self.entries_dir.iterdir()) if p.is_file()}
        return RawEntries(self.entries_url, datetime.now(UTC), docs, is_fixture=True)
