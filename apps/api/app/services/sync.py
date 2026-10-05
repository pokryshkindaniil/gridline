"""Diff/update engine: parsed sessions -> database.

Identity: Session = (event, external_id); Event = (season, external_id). Times are mutable
attributes, so rescheduling updates the same row (same id => same ICS UID) and records a
SessionChange per changed field.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from gridline_shared import SessionStatus, session_fingerprint, slugify
from gridline_sources import ParsedSession
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..models import Event, Season, Series, Session, SessionChange

log = logging.getLogger(__name__)

# Fields whose change affects calendar clients and so bumps SEQUENCE.
TRACKED = ("name", "session_type", "start_at", "end_at", "status")


@dataclass
class SyncStats:
    seen: int = 0
    inserted: int = 0
    updated: int = 0
    cancelled: int = 0
    warnings: list[str] = field(default_factory=list)  # data-quality notes (kept data, skipped risky changes)

    @property
    def changed(self) -> int:
        return self.inserted + self.updated + self.cancelled


def _iso(v: object) -> str | None:
    return v.isoformat() if isinstance(v, datetime) else (None if v is None else str(v))


def _get_season(db: DbSession, series: Series, year: int) -> Season:
    season = db.scalar(select(Season).where(Season.series_id == series.id, Season.year == year))
    if season is None:
        season = Season(series_id=series.id, year=year)
        db.add(season)
        db.flush()
    return season


def _event_dates(group: list[ParsedSession]) -> tuple:
    first = group[0]
    if first.event_start_date and first.event_end_date:
        return first.event_start_date, first.event_end_date
    tz = ZoneInfo(first.timezone)
    days = [s.start_at.astimezone(tz).date() for s in group]
    return min(days), max(days)


def _upsert_event(db: DbSession, season: Season, group: list[ParsedSession]) -> Event:
    p = group[0]
    start, end = _event_dates(group)
    event = db.scalar(select(Event).where(Event.season_id == season.id, Event.external_id == p.event_external_id))
    if event is None:
        slug = slugify(p.event_name)
        if db.scalar(select(Event.id).where(Event.season_id == season.id, Event.slug == slug)):
            slug = f"{slug}-{slugify(p.event_external_id)}"
        event = Event(season_id=season.id, external_id=p.event_external_id, slug=slug, name=p.event_name,
                      start_date=start, end_date=end, timezone=p.timezone)
        db.add(event)
    event.name = p.event_name
    event.circuit_name = p.circuit_name
    event.city = p.city
    event.country_code = p.country_code
    event.timezone = p.timezone
    event.start_date, event.end_date = start, end
    event.official_url = p.event_url
    db.flush()
    return event


def _collapse_duplicates(parsed: list[ParsedSession], stats: SyncStats) -> list[ParsedSession]:
    """Upstream sometimes repeats a record. Keep the first occurrence; never create phantom sessions."""
    seen: dict[tuple, ParsedSession] = {}
    for p in parsed:
        key = (p.season_year, p.event_external_id, p.external_id)
        first = seen.get(key)
        if first is None:
            seen[key] = p
        elif first.start_at != p.start_at:
            stats.warnings.append(f"conflicting duplicate {p.event_external_id}/{p.external_id}: kept first")
    return list(seen.values())


# Cancellation guard: if an event suddenly lists fewer than this fraction of the sessions we already
# hold, treat it as a damaged upstream page and do not cancel anything for that event.
EVENT_SHRINK_RATIO = 0.5


def apply_parsed_sessions(
    db: DbSession,
    series: Series,
    parsed: list[ParsedSession],
    *,
    source_name: str,
    now: datetime | None = None,
) -> SyncStats:
    now = now or datetime.now(UTC)
    stats = SyncStats(seen=len(parsed))

    parsed = _collapse_duplicates(parsed, stats)

    groups: dict[tuple[int, str], list[ParsedSession]] = {}
    for p in parsed:
        groups.setdefault((p.season_year, p.event_external_id), []).append(p)

    for (year, _event_key), group in groups.items():
        season = _get_season(db, series, year)
        event = _upsert_event(db, season, group)
        existing = {s.external_id: s for s in db.scalars(select(Session).where(Session.event_id == event.id))}
        incoming_ids = set()

        for p in group:
            incoming_ids.add(p.external_id)
            start = p.start_at.astimezone(UTC)
            end = p.end_at.astimezone(UTC) if p.end_at else None
            values = dict(name=p.session_name, session_type=str(p.session_type), start_at=start,
                          end_at=end, status=str(p.status))
            fp = session_fingerprint(p.session_name, str(p.session_type), start, end, str(p.status))
            row = existing.get(p.external_id)

            if row is None:
                db.add(Session(event_id=event.id, external_id=p.external_id, **values, source_url=p.source_url,
                               source_name=source_name, source_updated_at=p.source_updated_at,
                               checked_at=now, fingerprint=fp, sequence=0, created_at=now, updated_at=now))
                stats.inserted += 1
                continue

            if row.fingerprint != fp:
                for f in TRACKED:
                    old, new = getattr(row, f), values[f]
                    if old != new:
                        db.add(SessionChange(session_id=row.id, detected_at=now, field_name=f,
                                             old_value=_iso(old), new_value=_iso(new), source_url=p.source_url))
                        setattr(row, f, new)
                row.fingerprint = fp
                row.sequence += 1
                row.updated_at = now
                stats.updated += 1
            # Always refresh freshness/provenance, even when nothing changed.
            row.checked_at = now
            row.source_url = p.source_url
            row.source_name = source_name
            row.source_updated_at = p.source_updated_at

        # A future session that vanished from an event the source still lists => cancelled,
        # unless the event shrank suspiciously (then keep everything and warn).
        if existing and len(incoming_ids) < EVENT_SHRINK_RATIO * len(existing):
            stats.warnings.append(
                f"event {event.slug}: source lists {len(incoming_ids)} of {len(existing)} known sessions; "
                "cancellations skipped"
            )
            continue
        for ext_id, row in existing.items():
            if ext_id in incoming_ids or row.status in (SessionStatus.CANCELLED, SessionStatus.COMPLETED):
                continue
            if row.start_at <= now:
                continue
            db.add(SessionChange(session_id=row.id, detected_at=now, field_name="status",
                                 old_value=row.status, new_value=str(SessionStatus.CANCELLED),
                                 source_url=row.source_url))
            row.status = str(SessionStatus.CANCELLED)
            row.fingerprint = session_fingerprint(row.name, row.session_type, row.start_at, row.end_at, row.status)
            row.sequence += 1
            row.updated_at = now
            row.checked_at = now
            stats.cancelled += 1

    db.flush()
    return stats


__all__ = ["SyncStats", "apply_parsed_sessions"]
