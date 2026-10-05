from __future__ import annotations

import hashlib
import hmac
import secrets
import string
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from gridline_calendar import CalendarEvent, render_calendar
from gridline_shared import SessionStatus, SessionType
from sqlalchemy import select
from sqlalchemy.orm import Session as Db

from ..config import get_settings
from ..models import CalendarFeed, Series, Session
from .queries import sessions_stmt
from .series_visibility import public_only

ALPHABET = string.ascii_letters + string.digits
VALID_TYPES = {t.value for t in SessionType}


class FeedError(ValueError):
    pass


def new_public_token() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(10))


def new_edit_token() -> str:
    return secrets.token_urlsafe(24)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def verify_edit_token(feed: CalendarFeed, token: str | None) -> bool:
    return bool(token) and hmac.compare_digest(feed.edit_token_hash, hash_token(token))


def validate_timezone(tz: str) -> str:
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        raise FeedError(f"unknown timezone {tz!r}") from None
    return tz


def resolve_series(db: Db, slugs: list[str]) -> list[Series]:
    """Series a feed may contain: public ones only. A series that exists but is not public is reported exactly like an
    unknown one, so the public API does not confirm what is switched off."""
    found = list(db.scalars(select(Series).where(Series.slug.in_(set(slugs)), public_only())))
    missing = set(slugs) - {s.slug for s in found}
    if missing:
        raise FeedError(f"unknown series: {', '.join(sorted(missing))}")
    return found


def validate_types(types: list[str]) -> list[str]:
    bad = set(types) - VALID_TYPES
    if bad:
        raise FeedError(f"unknown session types: {', '.join(sorted(bad))}")
    return sorted(set(types))


def feed_calendar_events(db: Db, feed: CalendarFeed, now: datetime | None = None) -> list[CalendarEvent]:
    now = now or datetime.now(UTC)
    types = [t.session_type for t in feed.session_types]
    series_ids = [s.id for s in feed.series if s.public]  # a series switched off later disappears from old feeds too
    if not types or not series_ids:
        return []
    since = now - timedelta(days=get_settings().feed_lookback_days)
    rows = db.scalars(sessions_stmt().where(Series.id.in_(series_ids), Session.session_type.in_(types),
                                            Session.start_at >= since))
    return [to_calendar_event(s) for s in rows]


def to_calendar_event(s: Session) -> CalendarEvent:
    ev = s.event
    place = ", ".join(p for p in (ev.circuit_name, ev.city) if p) or None
    return CalendarEvent(
        session_id=s.id,
        series_short_name=ev.season.series.short_name,
        event_name=ev.name,
        session_name=s.name,
        session_type=SessionType(s.session_type),
        status=SessionStatus(s.status),
        start_at=s.start_at,
        end_at=s.end_at,
        sequence=s.sequence,
        last_modified=s.updated_at,
        source_name=s.source_name,
        source_url=s.source_url,
        checked_at=s.checked_at,
        location=place,
        event_timezone=ev.timezone,
    )


def render_feed(db: Db, feed: CalendarFeed, now: datetime | None = None) -> str:
    return render_calendar(feed_calendar_events(db, feed, now), name="GRIDLINE motorsport", timezone=feed.timezone)
