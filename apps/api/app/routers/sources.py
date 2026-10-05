"""/sources/health = health of the DATA (freshness of each upstream source).
Contrast with /health = is this API process (and its database) alive."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from gridline_sources import all_sources, supports_entries
from sqlalchemy import select
from sqlalchemy.orm import Session as Db

from ..config import get_settings
from ..db import get_db
from ..models import SourceRun
from ..schemas import EntriesHealthOut, SourceHealthOut
from ..services.health import RunView, classify
from ..services.series_visibility import public_series_slugs

router = APIRouter()


@router.get("/sources/health", response_model=list[SourceHealthOut])
def sources_health(db: Annotated[Db, Depends(get_db)]) -> list[SourceHealthOut]:
    settings = get_settings()
    now = datetime.now(UTC)
    out = []
    visible = public_series_slugs(db)  # a series that is switched off has no public source-health row either
    for src in (s for s in all_sources() if s.series_slug in visible):
        all_runs = list(db.scalars(
            select(SourceRun).where(SourceRun.source_id == src.source_id)
            .order_by(SourceRun.started_at.desc()).limit(100)
        ))
        runs = [r for r in all_runs if r.kind == "schedule"][:50]
        views = [RunView(r.status, r.mode, r.completed_at, r.started_at) for r in runs]
        status = classify(src.live, views, now, settings)
        wanted_mode = "live" if src.live else "fixture"
        last_ok = next((r for r in runs if r.mode == wanted_mode and r.status in ("success", "partial")), None)
        last_attempt = runs[0] if runs else None
        failed = last_attempt if last_attempt and last_attempt.status == "failed" else None
        partial = last_attempt if last_attempt and last_attempt.status == "partial" else None
        out.append(SourceHealthOut(
            source_id=src.source_id, series=src.series_slug, source_name=src.source_name,
            official_url=src.official_url, live=src.live, status=status,
            last_successful_sync=last_ok.completed_at if last_ok else None,
            last_attempt=last_attempt.started_at if last_attempt else None,
            records_seen=last_ok.records_seen if last_ok else None,
            records_changed=last_ok.records_changed if last_ok else None,
            last_error=(failed or partial).error if (failed or partial) else None,
            limitation=src.limitation,
            entries=_entries_health(src, [r for r in all_runs if r.kind == "entries"], now, settings),
        ))
    return out


def _entries_health(src, runs, now, settings) -> EntriesHealthOut | None:
    if not supports_entries(src):
        return None
    views = [RunView(r.status, r.mode, r.completed_at, r.started_at) for r in runs]
    status = classify(src.live, views, now, settings)
    last_ok = next((r for r in runs if r.mode == "live" and r.status in ("success", "partial")), None)
    last = runs[0] if runs else None
    bad = last if last and last.status in ("failed", "partial") else None
    return EntriesHealthOut(
        status=status, last_successful_sync=last_ok.completed_at if last_ok else None,
        last_attempt=last.started_at if last else None,
        records_seen=last_ok.records_seen if last_ok else None,
        records_changed=last_ok.records_changed if last_ok else None,
        last_error=bad.error if bad else None, limitation=src.entries_limitation,
    )
