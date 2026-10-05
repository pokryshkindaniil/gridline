"""Parse SRO GT World Challenge Europe event pages.

Each event page carries a schema.org SportsEvent JSON-LD block (name, dates, venue) and
one timetable table per day with columns: Session | Local Time | GMT.
"""

from __future__ import annotations

import html
import json
import re
from datetime import UTC, date, datetime, timedelta

from bs4 import BeautifulSoup
from gridline_shared import classify_session_type, slugify

from ..base import ParsedSession, ParseResult, RawSchedule, SourceError, SourceIssue, dedupe_external_ids

COUNTRY_INFO = {  # country name -> (ISO-3166 alpha-2, IANA tz)
    "Spain": ("ES", "Europe/Madrid"), "Portugal": ("PT", "Europe/Lisbon"),
    "Italy": ("IT", "Europe/Rome"), "France": ("FR", "Europe/Paris"),
    "Belgium": ("BE", "Europe/Brussels"), "Netherlands": ("NL", "Europe/Amsterdam"),
    "Germany": ("DE", "Europe/Berlin"), "United Kingdom": ("GB", "Europe/London"),
    "Great Britain": ("GB", "Europe/London"), "England": ("GB", "Europe/London"),
    "Austria": ("AT", "Europe/Vienna"),
}
DAY_RE = re.compile(r"(\d{1,2})\s+([A-Za-z]+)")
MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], start=1)}


def _jsonld(soup: BeautifulSoup) -> dict | None:
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "", strict=False)
        except json.JSONDecodeError:
            continue
        if data.get("@type") == "SportsEvent":
            return data
    return None


def _hhmm(text: str) -> tuple[int, int]:
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", text)
    if not m:
        raise SourceError(f"unparseable time {text!r}")
    return int(m[1]), int(m[2])


def _offset(local: tuple[int, int], gmt: tuple[int, int]) -> timedelta:
    """Local-minus-GMT difference, normalised to (-12h, +12h]."""
    minutes = (local[0] * 60 + local[1]) - (gmt[0] * 60 + gmt[1])
    minutes = (minutes + 720) % 1440 - 720
    return timedelta(minutes=minutes)


def parse_event(doc: str) -> list[ParsedSession]:
    soup = BeautifulSoup(doc, "lxml")
    ld = _jsonld(soup)
    if ld is None:
        raise SourceError("no SportsEvent JSON-LD found")
    try:
        url = ld["url"]
        event_id = "e" + re.search(r"/event/(\d+)/", url).group(1)  # type: ignore[union-attr]
        start_date = date.fromisoformat(ld["startDate"])
        end_date = date.fromisoformat(ld["endDate"])
        venue = html.unescape(ld["location"]["name"])
        name = html.unescape(ld["name"]).strip()
    except (KeyError, AttributeError, ValueError) as exc:
        raise SourceError(f"unexpected GTWC event JSON-LD: {exc}") from exc

    circuit, _, country = venue.rpartition(",")
    country = country.strip()
    if country not in COUNTRY_INFO:
        raise SourceError(f"event {event_id}: no maintained timezone mapping for country {country!r}; quarantined")
    cc, tz = COUNTRY_INFO[country]
    circuit = circuit.strip() or venue

    tables = soup.select("div.timetable__container")
    if not tables:
        raise SourceError(f"GTWC event {event_id}: no timetable found; markup changed?")

    sessions: list[ParsedSession] = []
    for table in tables:
        caption = table.select_one("caption span")
        m = DAY_RE.search(caption.get_text(" ", strip=True)) if caption else None
        if not m or m[2] not in MONTHS:
            raise SourceError(f"GTWC event {event_id}: bad day caption {caption!r}")
        day = date(start_date.year, MONTHS[m[2]], int(m[1]))
        for row in table.select("tbody tr"):
            cells = [c.get_text(" ", strip=True) for c in row.find_all("td")]
            if len(cells) < 3:
                continue
            title, local_s, gmt_s = cells[0], cells[1], cells[2]
            local, gmt = _hhmm(local_s), _hhmm(gmt_s)
            local_dt = datetime(day.year, day.month, day.day, *local)
            start = (local_dt - _offset(local, gmt)).replace(tzinfo=UTC)
            sessions.append(ParsedSession(
                season_year=start_date.year,
                event_external_id=event_id,
                event_name=name,
                timezone=tz,
                external_id=slugify(title),
                session_name=html.unescape(title),
                session_type=classify_session_type(title),
                start_at=start,
                source_url=url,
                circuit_name=circuit,
                country_code=cc,
                event_url=url,
                event_start_date=start_date,
                event_end_date=end_date,
            ))
    return sessions


def parse_events(raw: RawSchedule) -> ParseResult:
    result = ParseResult([])
    for label, doc in raw.documents.items():
        if label.endswith("calendar.html") or label == raw.source_url:
            continue  # the listing page, not an event
        try:
            result.sessions.extend(parse_event(doc))
        except (SourceError, KeyError, ValueError, TypeError) as exc:
            result.issues.append(SourceIssue(label.rsplit("/", 1)[-1], f"{type(exc).__name__}: {exc}"))
    if not result.sessions and not result.issues:
        raise SourceError("GTWC: no sessions parsed from any document")
    result.sessions = dedupe_external_ids(result.sessions)
    return result
