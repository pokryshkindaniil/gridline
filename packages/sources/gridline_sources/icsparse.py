"""Minimal iCalendar reader for the subset published by official calendar endpoints."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from .base import SourceError


@dataclass(frozen=True)
class IcsEvent:
    uid: str
    summary: str
    start: datetime  # timezone-aware
    end: datetime | None
    tzid: str | None  # TZID of DTSTART when given (None for UTC "Z" values)
    status: str | None


def _unfold(text: str) -> list[str]:
    return re.sub(r"\r?\n[ \t]", "", text).splitlines()


def _unescape(v: str) -> str:
    return v.replace("\\n", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")


def _dt(params: dict[str, str], value: str) -> tuple[datetime, str | None]:
    fmt = "%Y%m%dT%H%M%S"
    if value.endswith("Z"):
        return datetime.strptime(value[:-1], fmt).replace(tzinfo=UTC), None
    tzid = params.get("TZID")
    if not tzid:
        raise SourceError(f"floating time without TZID: {value!r}")
    return datetime.strptime(value, fmt).replace(tzinfo=ZoneInfo(tzid)), tzid


def parse_ics(text: str) -> list[IcsEvent]:
    if "BEGIN:VCALENDAR" not in text:
        raise SourceError("not an iCalendar document")
    events, cur = [], None
    for line in _unfold(text):
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line == "END:VEVENT" and cur is not None:
            try:
                s_params, s_val = cur["DTSTART"]
                start, tzid = _dt(s_params, s_val)
                end = _dt(*cur["DTEND"])[0] if "DTEND" in cur else None
                events.append(IcsEvent(
                    uid=cur["UID"][1], summary=_unescape(cur["SUMMARY"][1]), start=start, end=end,
                    tzid=tzid, status=cur.get("STATUS", ({}, None))[1],
                ))
            except KeyError as exc:
                raise SourceError(f"VEVENT missing {exc}") from exc
            cur = None
        elif cur is not None and ":" in line:
            head, value = line.split(":", 1)
            name, *plist = head.split(";")
            cur[name.upper()] = ({p.split("=", 1)[0].upper(): p.split("=", 1)[1] for p in plist if "=" in p}, value)
    return events
