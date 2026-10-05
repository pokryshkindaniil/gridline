"""Housekeeping. SessionChange history is NEVER deleted; only old SourceRun rows are pruned."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select

from .db import SessionLocal
from .models import SourceRun


def cleanup_source_runs(keep_days: int, db_factory=SessionLocal, now: datetime | None = None) -> int:
    """Delete SourceRun rows older than keep_days, always keeping each source's newest success and newest
    attempt per mode (health classification depends on them)."""
    cutoff = (now or datetime.now(UTC)) - timedelta(days=keep_days)
    with db_factory() as db:
        newest_ok = select(func.max(SourceRun.started_at)).where(SourceRun.status.in_(("success", "partial"))) \
            .group_by(SourceRun.source_id, SourceRun.mode)
        newest_any = select(func.max(SourceRun.started_at)).group_by(SourceRun.source_id, SourceRun.mode)
        res = db.execute(
            delete(SourceRun).where(
                SourceRun.started_at < cutoff,
                SourceRun.started_at.not_in(newest_ok),
                SourceRun.started_at.not_in(newest_any),
            )
        )
        db.commit()
        return res.rowcount or 0
