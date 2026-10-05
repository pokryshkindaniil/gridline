"""Source health classification. Pure; thresholds come from Settings, never hard-coded elsewhere."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ..config import Settings


@dataclass(frozen=True)
class RunView:
    status: str  # success | partial | failed | running
    mode: str
    completed_at: datetime | None
    started_at: datetime


def classify(live: bool, runs_newest_first: list[RunView], now: datetime, settings: Settings) -> str:
    """healthy | degraded | stale | failing | fixture_only"""
    if not live:
        return "fixture_only"
    live_runs = [r for r in runs_newest_first if r.mode == "live" and r.status != "running"]
    consecutive_failures = 0
    for r in live_runs:
        if r.status != "failed":
            break
        consecutive_failures += 1
    last_ok = next((r for r in live_runs if r.status in ("success", "partial")), None)
    max_age = timedelta(minutes=settings.source_healthy_max_age_minutes)
    fresh = bool(last_ok and last_ok.completed_at and now - last_ok.completed_at <= max_age)

    if consecutive_failures >= settings.source_failing_after_failures:
        return "failing"
    if consecutive_failures >= 1 and not fresh:
        return "failing"
    if not fresh:
        return "stale"
    return "degraded" if last_ok and last_ok.status == "partial" else "healthy"
