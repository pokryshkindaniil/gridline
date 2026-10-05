from __future__ import annotations

from pathlib import Path

from ..base import MotorsportSource, ParseResult, RawSchedule, SourceUnavailable
from .parser import parse_schedule


class ImsaSource(MotorsportSource):
    def __init__(self) -> None:
        self.source_id = "imsa"
        self.series_slug = "imsa-weathertech"
        self.source_name = "IMSA WeatherTech SportsCar Championship"
        self.official_url = "https://www.imsa.com/weathertech/schedule/"
        self.live = False
        self.fixture_label = "synthetic dev fixture"
        self.fixture_dir = Path(__file__).parent / "fixtures"
        self.limitation = (
            "imsa.com sits behind a Cloudflare bot challenge (HTTP 403 'Just a moment...'). GRIDLINE does "
            "not bypass bot protection, so no live adapter exists. The fixture is SYNTHETIC; it is not "
            "the real IMSA calendar. Contributors: look for an official calendar export the series permits."
        )

    async def fetch(self) -> RawSchedule:
        raise SourceUnavailable(f"imsa has no live adapter yet. {self.limitation}")

    def parse(self, raw: RawSchedule) -> ParseResult:
        return parse_schedule(raw)
