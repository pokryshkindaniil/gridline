"""Parse official WEC race pages + their ICS export.

Authoritative schedule = the ICS (stable per-session UID, local time + IANA TZID).
The page contributes the event name and cancellation status (JSON-LD eventStatus). Note: the page's own
`data-timestamp` epochs were found inconsistent with the ICS for some events (Le Mans) and are NOT used.
"""

from __future__ import annotations

import json
import re
from datetime import UTC

from bs4 import BeautifulSoup
from gridline_shared import SessionStatus, classify_session_type, slugify

from ..base import ParsedSession, ParseResult, RawSchedule, SourceError, SourceIssue
from ..icsparse import parse_ics

SITE = "https://www.fiawec.com"
SLUG_YEAR = re.compile(r"race_(.+-(\d{4}))\.(html|ics)$")
COUNTRY = {"JPN": "JP", "FRA": "FR", "ESP": "ES", "ITA": "IT", "BEL": "BE", "BRA": "BR", "USA": "US",
           "QAT": "QA", "BHR": "BH", "GBR": "GB", "GER": "DE", "DEU": "DE", "POR": "PT"}


# Maintained circuit -> IANA zone map, used only when the ICS gives UTC instants without a TZID.
CIRCUIT_TZ = {
    "le-mans": "Europe/Paris", "fuji": "Asia/Tokyo", "imola": "Europe/Rome", "monza": "Europe/Rome",
    "spa-francorchamps": "Europe/Brussels", "barcelona": "Europe/Madrid", "sao-paulo": "America/Sao_Paulo",
    "lone-star-le-mans": "America/Chicago", "bahrain": "Asia/Bahrain", "qatar": "Asia/Qatar",
    "silverstone": "Europe/London", "portimao": "Europe/Lisbon",
}


def circuit_timezone(slug: str) -> str | None:
    for key, tz in CIRCUIT_TZ.items():
        if key in slug:
            return tz
    return None


def _page(html: str) -> tuple[str, dict[str, SessionStatus], str | None, str | None]:
    if "FETCH-ERROR" in html[:200]:
        raise SourceError(html.strip("<!-> \n"))
    soup = BeautifulSoup(html, "lxml")
    ld = None
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "", strict=False)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "SportsEvent":
            ld = data
            break
    if ld is None:
        raise SourceError("no SportsEvent JSON-LD on race page")
    name = re.sub(r"^WEC\s+|\s+\d{4}$", "", ld["name"]).strip()
    statuses: dict[str, SessionStatus] = {}
    for sub in ld.get("subEvent", []):
        label = re.sub(rf"\s+-\s+{re.escape(name)}$", "", sub["name"])
        if sub.get("eventStatus", "").endswith("EventCancelled"):
            statuses[label] = SessionStatus.CANCELLED
    loc = ld.get("location", {}).get("name")
    addr = (ld.get("location", {}).get("address") or "").rsplit(",", 1)[-1].strip()
    return name, statuses, loc, COUNTRY.get(addr)


def parse_event(slug: str, year: int, html: str, ics: str | None) -> list[ParsedSession]:
    name, statuses, place, country = _page(html)
    if ics is None:
        raise SourceError("race page has no calendar (ICS) link")
    events = parse_ics(ics)
    if not events:
        raise SourceError("ICS contains no events")

    url = f"{SITE}/en/race/{slug}"
    out = []
    for e in events:
        tz = e.tzid or circuit_timezone(slug)
        if tz is None:
            raise SourceError(f"ICS event {e.uid} is UTC-only and {slug!r} is not in the circuit timezone map; quarantined")
        prefix = f"{name} - "
        if not e.summary.startswith(prefix):
            raise SourceError(f"unexpected ICS summary {e.summary!r}")
        sname = e.summary[len(prefix):]
        status = statuses.get(sname, SessionStatus.SCHEDULED)
        if e.status and e.status.upper() == "CANCELLED":
            status = SessionStatus.CANCELLED
        out.append(ParsedSession(
            season_year=year,
            event_external_id=slug,
            event_name=name,
            timezone=tz,
            external_id=slugify(e.uid.split("@", 1)[0]),
            session_name=sname,
            session_type=classify_session_type(sname),
            start_at=e.start.astimezone(UTC),
            end_at=e.end.astimezone(UTC) if e.end else None,
            status=status,
            source_url=url,
            circuit_name=place,
            country_code=country,
            event_url=url,
        ))
    return out


def parse_events(raw: RawSchedule) -> ParseResult:
    pages: dict[str, tuple[int, str]] = {}
    ics: dict[str, str] = {}
    for label, doc in raw.documents.items():
        m = SLUG_YEAR.search(label)
        if not m:
            continue
        if m[3] == "html":
            pages[m[1]] = (int(m[2]), doc)
        else:
            ics[m[1]] = doc
    result = ParseResult([])
    for slug, (year, html) in sorted(pages.items()):
        try:
            result.sessions.extend(parse_event(slug, year, html, ics.get(slug)))
        except (SourceError, KeyError, ValueError, TypeError) as exc:
            result.issues.append(SourceIssue(slug, f"{type(exc).__name__}: {exc}"))
    if not pages:
        raise SourceError("WEC: no race documents to parse")
    return result
