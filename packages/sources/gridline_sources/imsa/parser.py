"""Parse the IMSA fixture (synthetic JSON). Replace with a real parser when a live source exists."""

from __future__ import annotations

import json
from datetime import date, datetime

from gridline_shared import classify_session_type, slugify

from ..base import ParsedSession, ParseResult, RawSchedule, SourceError, dedupe_external_ids


def parse_schedule(raw: RawSchedule) -> ParseResult:
    out: list[ParsedSession] = []
    for name, body in raw.documents.items():
        if not name.endswith(".json"):
            continue
        try:
            data = json.loads(body)
            year = int(data["season"])
            for ev in data["events"]:
                for s in ev["sessions"]:
                    out.append(ParsedSession(
                        season_year=year,
                        event_external_id=ev["id"],
                        event_name=ev["name"],
                        timezone=ev["timezone"],
                        external_id=slugify(s["name"]),
                        session_name=s["name"],
                        session_type=classify_session_type(s["name"]),
                        start_at=datetime.fromisoformat(s["start"]),
                        end_at=datetime.fromisoformat(s["end"]) if s.get("end") else None,
                        source_url=ev.get("url", raw.source_url),
                        circuit_name=ev.get("circuit"),
                        city=ev.get("city"),
                        country_code=ev.get("country"),
                        event_url=ev.get("url"),
                        event_start_date=date.fromisoformat(ev["start"]),
                        event_end_date=date.fromisoformat(ev["end"]),
                    ))
        except (KeyError, ValueError, TypeError) as exc:
            raise SourceError(f"unexpected IMSA fixture format in {name}: {exc}") from exc
    return ParseResult(dedupe_external_ids(out))
