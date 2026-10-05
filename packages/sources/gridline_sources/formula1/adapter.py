from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from pathlib import Path

from .. import base
from ..base import MotorsportSource, ParseResult, RawSchedule
from ..entries import EntryFetchPlan, EntryParseResult, RawEntries
from . import roster
from .parser import parse_races

SITE = "https://www.formula1.com"


class Formula1Source(MotorsportSource):
    def __init__(self) -> None:
        self.year: int | None = None  # override for tests / backfills
        self.source_id = "formula1"
        self.series_slug = "formula-1"
        self.source_name = "Formula 1 (formula1.com)"
        self.official_url = f"{SITE}/en/racing/{datetime.now(UTC).year}"
        self.fixture_dir = Path(__file__).parent / "fixtures"
        self.entries_dir = Path(__file__).parent / "fixtures_roster"
        self.entries_url = f"{SITE}/en/teams"
        self.entries_label = "season roster"
        self.entries_limitation = (
            "Season-wide roster from formula1.com (teams, chassis, standings table, race results, driver profiles): "
            "no roster API is published. Race numbers come from the latest race result, so they are empty before the "
            "first race; reserve drivers are text-only on the site and are not imported."
        )
        self.limitation = (
            "Parses schema.org JSON-LD embedded in the official race pages (no API is published). "
            "The timezone comes from the page's embedded meeting data; pre-season testing pages are skipped."
        )

    async def fetch(self) -> RawSchedule:
        year = self.year or datetime.now(UTC).year
        index_url = f"{SITE}/en/racing/{year}"
        docs: dict[str, str] = {}
        async with base.http_client(self.transport) as client:
            index = await base.http_get(client, index_url)
            slugs = sorted(set(re.findall(rf"/en/racing/{year}/([a-z0-9-]+)", index)))
            slugs = [s for s in slugs if not s.startswith("pre-season-testing")]
            if not slugs:
                raise base.SourceError(f"F1 index {index_url} lists no race pages; markup changed?")
            for slug in slugs:
                url = f"{index_url}/{slug}"
                try:
                    docs[url] = await base.http_get(client, url)
                except base.SourceError as exc:
                    docs[url] = f"<!-- FETCH-ERROR {exc} -->"  # reported per event by the parser
                await asyncio.sleep(self.request_delay)
        return RawSchedule(index_url, datetime.now(UTC), docs)

    def parse(self, raw: RawSchedule) -> ParseResult:
        return parse_races(raw)

    # ---- EntryListSource capability (season-wide roster) ----------------------------------------
    async def fetch_entries(self, plan: EntryFetchPlan) -> RawEntries:
        year = self.year or datetime.now(UTC).year
        docs: dict[str, str] = {}
        async with base.http_client(self.transport) as client:

            async def get(key: str, url: str, *, required: bool = False) -> None:
                try:
                    docs[key] = await base.http_get(client, url)
                except base.SourceError as exc:
                    if required:
                        raise
                    docs[key] = f"<!-- FETCH-ERROR {exc} -->"  # reported per team by the parser
                await asyncio.sleep(self.request_delay)

            await get(roster.TEAMS_KEY, f"{SITE}/en/teams", required=True)
            teams = roster.parse_team_index(docs[roster.TEAMS_KEY])
            await get(roster.STANDINGS_KEY, f"{SITE}/en/results/{year}/drivers", required=True)
            driver_slugs: list[str] = []
            for slug, _name in teams:
                await get(roster.team_key(slug), f"{SITE}/en/teams/{slug}")
                if "FETCH-ERROR" not in docs[roster.team_key(slug)][:200]:
                    driver_slugs += [d for d in roster.parse_team_page(docs[roster.team_key(slug)])["drivers"]
                                     if d not in driver_slugs]
            for d in driver_slugs:
                await get(roster.driver_key(d), f"{SITE}/en/drivers/{d}")
            try:
                await get(roster.RACES_KEY, f"{SITE}/en/results/{year}/races", required=True)
                for race_id, path in roster.parse_race_index(docs[roster.RACES_KEY])[: roster.MAX_RESULT_PAGES]:
                    await get(roster.result_key(race_id), SITE + path)
            except base.SourceError:
                docs.pop(roster.RACES_KEY, None)  # no race results yet (pre-season): numbers stay empty
        return RawEntries(f"{SITE}/en/teams", datetime.now(UTC), docs)

    def parse_entries(self, raw: RawEntries) -> EntryParseResult:
        return roster.parse_roster(raw, self.year or datetime.now(UTC).year)

    def load_entries_fixture(self) -> RawEntries:
        docs = {p.name: p.read_text(encoding="utf-8") for p in sorted(self.entries_dir.iterdir()) if p.is_file()}
        return RawEntries(self.entries_url, datetime.now(UTC), docs, is_fixture=True)
