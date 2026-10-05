"""Standards-compliant (RFC 5545) iCalendar rendering. Pure: no DB, no I/O.

Design notes
- Instants are emitted in UTC (DTSTART:...Z). Clients render them in the viewer's local zone; the
  feed's preferred timezone is advertised via X-WR-TIMEZONE and used in the human description.
- UID is derived from the session's permanent id, so a rescheduled session updates in place.
- SEQUENCE increments on schedule-affecting changes; LAST-MODIFIED is the last real change.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from gridline_shared import SessionStatus, SessionType

PRODID = "-//GRIDLINE//Motorsport Calendar//EN"

DEFAULT_DURATION = {
    SessionType.PRACTICE: timedelta(hours=1),
    SessionType.QUALIFYING: timedelta(hours=1),
    SessionType.SPRINT: timedelta(minutes=45),
    SessionType.RACE: timedelta(hours=2),
    SessionType.WARMUP: timedelta(minutes=30),
    SessionType.TEST: timedelta(hours=1),
    SessionType.OTHER: timedelta(hours=1),
}


def uid_for_session(session_id: object) -> str:
    return f"session-{session_id}@gridline"


@dataclass(frozen=True)
class CalendarEvent:
    session_id: object
    series_short_name: str
    event_name: str
    session_name: str
    session_type: SessionType
    status: SessionStatus
    start_at: datetime
    end_at: datetime | None
    sequence: int
    last_modified: datetime
    source_name: str
    source_url: str
    checked_at: datetime
    location: str | None = None
    event_timezone: str | None = None


def _escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
        .replace("\r\n", "\\n").replace("\n", "\\n")
    )


def _fold(line: str) -> list[str]:
    """Fold to <=75 octets per line, never splitting a UTF-8 sequence."""
    raw = line.encode()
    if len(raw) <= 75:
        return [line]
    out: list[str] = []
    cur = b""
    limit = 75
    for ch in line:
        b = ch.encode()
        if len(cur) + len(b) > limit:
            out.append(cur.decode())
            cur, limit = b"", 74  # continuation lines start with a space
        cur += b
    out.append(cur.decode())
    return [out[0]] + [" " + p for p in out[1:]]


def _utc(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _summary(ev: CalendarEvent) -> str:
    base = f"{ev.series_short_name} · {ev.event_name} · {ev.session_name}"
    return f"CANCELLED: {base}" if ev.status == SessionStatus.CANCELLED else base


def _description(ev: CalendarEvent, tz: ZoneInfo, tz_name: str) -> str:
    local = ev.start_at.astimezone(tz)
    lines = [
        "Official schedule",
        f"Source: {ev.source_name}",
        f"Verified: {ev.checked_at.astimezone(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        f"Starts: {local.strftime('%a %-d %b %H:%M')} ({tz_name})",
    ]
    if ev.event_timezone and ev.event_timezone != tz_name:
        circuit = ev.start_at.astimezone(ZoneInfo(ev.event_timezone))
        lines.append(f"Circuit time: {circuit.strftime('%H:%M')} ({ev.event_timezone})")
    if ev.status == SessionStatus.DELAYED:
        lines.append("Status: delayed")
    lines.append(ev.source_url)
    return "\n".join(lines)


def render_calendar(
    events: list[CalendarEvent],
    *,
    name: str = "GRIDLINE",
    timezone: str = "UTC",
    refresh_interval: timedelta = timedelta(hours=1),
) -> str:
    tz = ZoneInfo(timezone)
    uids = [uid_for_session(e.session_id) for e in events]
    if len(uids) != len(set(uids)):
        raise ValueError("duplicate session ids: a calendar must not contain duplicate UIDs")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(name)}",
        f"X-WR-TIMEZONE:{timezone}",
        f"REFRESH-INTERVAL;VALUE=DURATION:PT{int(refresh_interval.total_seconds() // 3600)}H",
        f"X-PUBLISHED-TTL:PT{int(refresh_interval.total_seconds() // 3600)}H",
    ]
    for ev in sorted(events, key=lambda e: (e.start_at, str(e.session_id))):
        end = ev.end_at or ev.start_at + DEFAULT_DURATION[ev.session_type]
        status = "CANCELLED" if ev.status == SessionStatus.CANCELLED else "CONFIRMED"
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid_for_session(ev.session_id)}",
            f"DTSTAMP:{_utc(ev.last_modified)}",
            f"LAST-MODIFIED:{_utc(ev.last_modified)}",
            f"SEQUENCE:{ev.sequence}",
            f"DTSTART:{_utc(ev.start_at)}",
            f"DTEND:{_utc(end)}",
            f"SUMMARY:{_escape(_summary(ev))}",
            f"DESCRIPTION:{_escape(_description(ev, tz, timezone))}",
            f"URL:{ev.source_url}",
            f"STATUS:{status}",
            "TRANSP:TRANSPARENT",
        ]
        if ev.location:
            lines.append(f"LOCATION:{_escape(ev.location)}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    folded = [part for line in lines for part in _fold(line)]
    return "\r\n".join(folded) + "\r\n"
