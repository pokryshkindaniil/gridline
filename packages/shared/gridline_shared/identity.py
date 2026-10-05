"""Identity and classification helpers.

Session identity is deliberately independent of start time: a session is
identified by (series, season, event key, session key). Times are mutable
attributes, never part of the identity.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime

from .enums import SessionType


def slugify(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def classify_session_type(name: str) -> SessionType:
    """Map a free-text session name onto the normalised GRIDLINE session types."""
    n = name.lower()
    if "warm" in n:
        return SessionType.WARMUP
    if any(k in n for k in ("qualif", "hyperpole", "superpole", "shootout", "pole")):
        return SessionType.QUALIFYING
    if "sprint" in n:
        return SessionType.SPRINT
    if "race" in n:
        return SessionType.RACE
    if "practice" in n or re.search(r"\bfp\s?\d", n):
        return SessionType.PRACTICE
    if "test" in n:
        return SessionType.TEST
    return SessionType.OTHER


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def session_fingerprint(
    name: str,
    session_type: str,
    start_at: datetime,
    end_at: datetime | None,
    status: str,
) -> str:
    """Hash of every schedule-relevant attribute; changes iff the schedule changes."""
    payload = "|".join([name, str(session_type), _iso(start_at), _iso(end_at), str(status)])
    return hashlib.sha256(payload.encode()).hexdigest()[:32]
