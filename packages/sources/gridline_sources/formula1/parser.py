"""Parse official formula1.com race pages.

Each race page embeds one schema.org SportsEvent JSON-LD with `subEvent` sessions (UTC start/end
and eventStatus) and Next.js flight data containing the circuit's IANA `timezone` and `gmtOffset`.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from gridline_shared import SessionStatus, classify_session_type, slugify

from ..base import ParsedSession, ParseResult, RawSchedule, SourceError, SourceIssue

TZ_RE = re.compile(r'timezone\\?":\\?"([A-Za-z_]+(?:/[A-Za-z_\-]+){1,2})')
OFFSET_RE = re.compile(r'gmtOffset\\?":\\?"([+-]\d{2}):(\d{2})')
SLUG_RE = re.compile(r"/racing/(\d{4})/([a-z0-9-]+)")
COUNTRY_CODES = {  # trailing country of the JSON-LD address; informational only (never used for time)
    "Australia": "AU", "China": "CN", "Japan": "JP", "USA": "US", "United States": "US", "Canada": "CA",
    "Monaco": "MC", "Spain": "ES", "Austria": "AT", "UK": "GB", "United Kingdom": "GB", "Belgium": "BE",
    "Hungary": "HU", "Netherlands": "NL", "Italy": "IT", "Azerbaijan": "AZ", "Singapore": "SG",
    "Mexico": "MX", "Brazil": "BR", "UAE": "AE", "United Arab Emirates": "AE", "Qatar": "QA",
    "Bahrain": "BH", "Saudi Arabia": "SA", "Malaysia": "MY",
}


def _status(value: str | None) -> SessionStatus:
    v = (value or "").rsplit("/", 1)[-1]
    if v == "EventCancelled":
        return SessionStatus.CANCELLED
    if v in ("EventPostponed", "EventRescheduled"):
        return SessionStatus.DELAYED
    return SessionStatus.SCHEDULED  # Completed/Scheduled: "completed" is derived from time


def _utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise SourceError(f"timestamp without offset: {value!r}")
    return dt.astimezone(UTC)


def _ld_event(soup: BeautifulSoup) -> dict | None:
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "", strict=False)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "SportsEvent" and data.get("subEvent"):
            return data
    return None


def parse_race(label: str, doc: str) -> list[ParsedSession]:
    if "FETCH-ERROR" in doc[:200]:
        raise SourceError(doc.strip("<!-> \n"))
    soup = BeautifulSoup(doc, "lxml")
    ld = _ld_event(soup)
    if ld is None:
        raise SourceError("no SportsEvent JSON-LD with sessions found")

    m = SLUG_RE.search(ld.get("@id", "")) or SLUG_RE.search(label)
    if not m:
        raise SourceError("cannot determine race slug/year")
    year, slug = int(m[1]), m[2]

    tz_match = TZ_RE.search(doc)
    if not tz_match:
        raise SourceError("no IANA timezone in embedded page data; event quarantined (no UTC guess)")
    tz = tz_match[1]
    try:
        zone = ZoneInfo(tz)
    except Exception as exc:
        raise SourceError(f"unknown timezone {tz!r}") from exc

    subs = ld["subEvent"]
    first_start = _utc(subs[0]["startDate"])
    off = OFFSET_RE.search(doc)
    if off:  # cross-check the IANA zone against the page's own UTC offset
        sign = -1 if off[1].startswith("-") else 1
        expected = sign * (abs(int(off[1])) * 60 + int(off[2]))
        actual = int(first_start.astimezone(zone).utcoffset().total_seconds() // 60)  # type: ignore[union-attr]
        if expected != actual:
            raise SourceError(f"timezone {tz} (UTC{actual:+d}min) disagrees with page gmtOffset {off[0]}")

    names = [s["name"] for s in subs]
    suffixes = {n.split(" - ", 1)[1] for n in names if " - " in n}
    event_name = suffixes.pop() if len(suffixes) == 1 else slug.replace("-", " ").title()
    loc = ld.get("location", {})
    city = loc.get("name")
    country = (loc.get("address") or "").rsplit(",", 1)[-1].strip()

    out = []
    for s in subs:
        sid = s["@id"].split("#", 1)[1] if "#" in s["@id"] else slugify(s["name"])
        sname = s["name"].split(" - ", 1)[0]
        out.append(ParsedSession(
            season_year=year,
            event_external_id=slug,
            event_name=event_name,
            timezone=tz,
            external_id=slugify(sid),
            session_name=sname,
            session_type=classify_session_type(sname),
            start_at=_utc(s["startDate"]),
            end_at=_utc(s["endDate"]) if s.get("endDate") else None,
            status=_status(s.get("eventStatus")),
            source_url=f"https://www.formula1.com/en/racing/{year}/{slug}",
            circuit_name=None,
            city=city,
            country_code=COUNTRY_CODES.get(country),
            event_url=f"https://www.formula1.com/en/racing/{year}/{slug}",
        ))
    return out


def parse_races(raw: RawSchedule) -> ParseResult:
    result = ParseResult([])
    for label, doc in raw.documents.items():
        if label.endswith("index.html") or re.fullmatch(r".*/racing/\d{4}", label):
            continue
        try:
            result.sessions.extend(parse_race(label, doc))
        except (SourceError, KeyError, ValueError, TypeError) as exc:
            result.issues.append(SourceIssue(label.rsplit("/", 1)[-1], f"{type(exc).__name__}: {exc}"))
    if not result.sessions and not result.issues:
        raise SourceError("F1: no race documents to parse")
    return result
