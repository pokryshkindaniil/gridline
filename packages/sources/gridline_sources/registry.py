from __future__ import annotations

from .base import MotorsportSource
from .fia_wec.adapter import FiaWecSource
from .formula1.adapter import Formula1Source
from .gt_world_challenge.adapter import GtWorldChallengeSource
from .imsa.adapter import ImsaSource

_SOURCES: dict[str, MotorsportSource] = {
    s.source_id: s for s in (Formula1Source(), FiaWecSource(), ImsaSource(), GtWorldChallengeSource())
}


def get_source(source_id: str) -> MotorsportSource:
    try:
        return _SOURCES[source_id]
    except KeyError:
        raise KeyError(f"unknown source {source_id!r}; known: {', '.join(_SOURCES)}") from None


def all_sources() -> list[MotorsportSource]:
    return list(_SOURCES.values())
