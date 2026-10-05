"""Adapter contract. Every championship implements MotorsportSource and
normalises into ParsedSession. Adapters never touch the database."""

from __future__ import annotations

import abc
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from gridline_shared import SessionStatus, SessionType

USER_AGENT = "GRIDLINE/0.1 (motorsport calendar; private development; schedule and entry-list sync)"


class SourceError(RuntimeError):
    """Raised when a source cannot be fetched or parsed. Never swallowed."""


class SourceUnavailable(SourceError):
    """The adapter has no legitimate live source (fixture-only)."""


@dataclass(frozen=True)
class RawSchedule:
    """Raw, unparsed payloads keyed by name (URL for live fetches, filename for fixtures)."""

    source_url: str
    fetched_at: datetime
    documents: dict[str, str]
    is_fixture: bool = False


@dataclass(frozen=True)
class SourceIssue:
    """A problem confined to one event (or the whole source). The event is quarantined, not guessed."""

    event: str | None
    message: str


@dataclass
class ParseResult:
    sessions: list[ParsedSession]
    issues: list[SourceIssue] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedSession:
    """Normalised session. start_at/end_at MUST be timezone-aware (converted to UTC by sync)."""

    season_year: int
    event_external_id: str
    event_name: str
    timezone: str  # IANA name of the circuit/event
    external_id: str  # stable session key within the event; never contains a time
    session_name: str
    session_type: SessionType
    start_at: datetime
    source_url: str
    end_at: datetime | None = None
    circuit_name: str | None = None
    city: str | None = None
    country_code: str | None = None
    event_url: str | None = None
    event_start_date: date | None = None
    event_end_date: date | None = None
    status: SessionStatus = SessionStatus.SCHEDULED
    source_updated_at: datetime | None = None

    def __post_init__(self) -> None:
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError, KeyError) as exc:
            raise ValueError(f"invalid IANA timezone {self.timezone!r} ({self.external_id})") from exc
        if self.start_at.tzinfo is None:
            raise ValueError(f"start_at must be timezone-aware ({self.external_id})")
        if self.end_at is not None and self.end_at.tzinfo is None:
            raise ValueError(f"end_at must be timezone-aware ({self.external_id})")


def dedupe_external_ids(sessions: list[ParsedSession]) -> list[ParsedSession]:
    """Deterministically suffix repeated session keys within one event (-2, -3 ...)."""
    from dataclasses import replace

    seen: Counter[tuple[str, str]] = Counter()
    out: list[ParsedSession] = []
    for s in sessions:
        key = (s.event_external_id, s.external_id)
        seen[key] += 1
        out.append(s if seen[key] == 1 else replace(s, external_id=f"{s.external_id}-{seen[key]}"))
    return out


class MotorsportSource(abc.ABC):
    """One championship = one adapter. Subclasses set these attributes in __init__."""

    source_id: str
    series_slug: str
    source_name: str  # shown to users, e.g. "GT World Challenge Europe (SRO)"
    official_url: str
    live: bool = True  # False: no legitimate live source, fixture-only
    fixture_label: str = "fixture snapshot"
    fixture_dir: Path
    limitation: str | None = None
    transport: httpx.AsyncBaseTransport | None = None  # tests inject httpx.MockTransport
    request_delay: float = 0.4  # politeness delay between requests of one sync

    @abc.abstractmethod
    async def fetch(self) -> RawSchedule:
        """Fetch the raw schedule from the official source."""

    @abc.abstractmethod
    def parse(self, raw: RawSchedule) -> ParseResult:
        """Pure function: raw payloads -> normalised sessions plus per-event issues.

        Event-level failures must be reported as SourceIssue (that event is quarantined) so one bad
        event never hides the rest. Raise SourceError only when the whole payload is unusable."""

    def load_fixture(self) -> RawSchedule:
        docs = {
            p.name: p.read_text(encoding="utf-8")
            for p in sorted(self.fixture_dir.iterdir())
            if p.is_file() and not p.name.startswith(".")
        }
        if not docs:
            raise SourceError(f"{self.source_id}: no fixtures in {self.fixture_dir}")
        return RawSchedule(self.official_url, datetime.now(UTC), docs, is_fixture=True)

    def display_name(self, raw: RawSchedule) -> str:
        return f"{self.source_name} ({self.fixture_label})" if raw.is_fixture else self.source_name


async def http_get(client: httpx.AsyncClient, url: str) -> str:
    try:
        resp = await client.get(url)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise SourceError(f"GET {url} failed: {exc}") from exc
    return resp.text


def http_client(transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
        timeout=httpx.Timeout(20.0),
        follow_redirects=True,
        transport=transport,
    )
