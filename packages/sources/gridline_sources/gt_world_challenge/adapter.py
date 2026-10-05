from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from pathlib import Path

from .. import base
from ..base import MotorsportSource, ParseResult, RawSchedule
from ..entries import EntryFetchPlan, EntryParseResult, RawEntries
from .entries import calendar_event_ids, doc_key, index_links, parse_entry_documents
from .parser import parse_events

SITE = "https://www.gt-world-challenge-europe.com"


class GtWorldChallengeSource(MotorsportSource):
    def __init__(self) -> None:
        self.source_id = "gt_world_challenge"
        self.series_slug = "gt-world-challenge-europe"
        self.source_name = "GT World Challenge Europe (SRO)"
        self.official_url = f"{SITE}/calendar"
        self.fixture_dir = Path(__file__).parent / "fixtures"
        self.limitation = (
            "Parses the public per-event timetables on the official site (static HTML + JSON-LD). "
            "If SRO changes the markup the parser fails loudly rather than guessing."
        )
        self.entries_url = f"{SITE}/entry-lists"
        self.entries_dir = Path(__file__).parent / "entry_fixtures"
        self.entries_limitation = (
            "Entry lists are the per-event tables SRO publishes (Driver 1..N in published order). A list appears "
            "only once SRO publishes it, so future events are empty until then. SRO publishes no per-driver "
            "session assignment: results pages list the whole crew for every session, so none is stored."
        )

    async def fetch(self) -> RawSchedule:
        docs: dict[str, str] = {}
        async with base.http_client(self.transport) as client:
            calendar_html = await base.http_get(client, self.official_url)
            paths = sorted(set(re.findall(r'href="(/event/\d+/[^"]+)"', calendar_html)))
            if not paths:
                raise base.SourceError("GTWC calendar page lists no /event/ links; markup changed?")
            for path in paths:
                url = SITE + path
                docs[url] = await base.http_get(client, url)
                await asyncio.sleep(self.request_delay)
        return RawSchedule(self.official_url, datetime.now(UTC), docs)

    def parse(self, raw: RawSchedule) -> ParseResult:
        return parse_events(raw)

    # ---- EntryListSource capability -------------------------------------------------------------
    async def fetch_entries(self, plan: EntryFetchPlan) -> RawEntries:
        docs: dict[str, str] = {}
        errors: dict[str, str] = {}
        async with base.http_client(self.transport) as client:
            docs["entry-lists.html"] = index = await base.http_get(client, self.entries_url)
            docs["calendar.html"] = calendar = await base.http_get(client, self.official_url)
            ids = calendar_event_ids(calendar)
            for slug, path in sorted(index_links(index).items()):
                if ids.get(slug) in plan.settled_events:
                    continue
                try:
                    docs[doc_key(slug)] = await base.http_get(client, SITE + path)
                except base.SourceError as exc:
                    errors[slug] = str(exc)
                await asyncio.sleep(self.request_delay)
        return RawEntries(self.entries_url, datetime.now(UTC), docs, fetch_errors=errors)

    def parse_entries(self, raw: RawEntries) -> EntryParseResult:
        return parse_entry_documents(raw)

    def load_entries_fixture(self) -> RawEntries:
        docs = {p.name: p.read_text(encoding="utf-8") for p in sorted(self.entries_dir.iterdir()) if p.is_file()}
        docs["calendar.html"] = (self.fixture_dir / "calendar.html").read_text(encoding="utf-8")
        return RawEntries(self.entries_url, datetime.now(UTC), docs, is_fixture=True)
