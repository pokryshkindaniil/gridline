from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from gridline_shared import SessionType
from gridline_sources import MotorsportSource, ParsedSession, ParseResult, RawSchedule

T0 = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def make_sessions(n: int, event: str = "e1", base: datetime = T0, tz: str = "Europe/Madrid") -> list[ParsedSession]:
    return [
        ParsedSession(
            season_year=2026, event_external_id=event, event_name=f"Event {event}", timezone=tz,
            external_id=f"s{i}", session_name=f"Session {i}", session_type=SessionType.PRACTICE,
            start_at=base + timedelta(days=30, hours=i), source_url="https://example.org/" + event,
            event_start_date=date(2026, 10, 31), event_end_date=date(2026, 11, 2),
        )
        for i in range(n)
    ]


class FakeSource(MotorsportSource):
    """Scripted adapter: `result` may be a ParseResult or an Exception to raise from parse()."""

    def __init__(self, result=None, fetch_error: Exception | None = None, delay: float = 0.0) -> None:
        self.source_id = "gt_world_challenge"  # any registered series slug works with the catalogue
        self.series_slug = "gt-world-challenge-europe"
        self.source_name = "Fake source"
        self.official_url = "https://example.org"
        self.fixture_dir = Path(".")
        self.result = result
        self.fetch_error = fetch_error
        self.delay = delay

    async def fetch(self) -> RawSchedule:
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fetch_error:
            raise self.fetch_error
        return RawSchedule(self.official_url, datetime.now(UTC), {"x": ""})

    def parse(self, raw: RawSchedule) -> ParseResult:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeEntrySource(FakeSource):
    """Scripted entries capability. `entries_result` is an EntryParseResult or an Exception raised by parse_entries()."""

    def __init__(self, entries_result=None, fetch_error: Exception | None = None) -> None:
        super().__init__()
        self.entries_result = entries_result
        self.entries_fetch_error = fetch_error
        self.entries_url = "https://example.org/entries"
        self.entries_limitation = None
        self.plans: list = []

    async def fetch_entries(self, plan):
        from gridline_sources import RawEntries

        self.plans.append(plan)
        if self.entries_fetch_error:
            raise self.entries_fetch_error
        return RawEntries(self.entries_url, datetime.now(UTC), {"x": ""})

    def parse_entries(self, raw):
        if isinstance(self.entries_result, Exception):
            raise self.entries_result
        return self.entries_result

    def load_entries_fixture(self):
        from gridline_sources import RawEntries

        return RawEntries(self.entries_url, datetime.now(UTC), {"x": ""}, is_fixture=True)
