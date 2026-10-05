"""Source sync orchestration."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from gridline_sources import EntryFetchPlan, MotorsportSource, all_sources, get_source, supports_entries
from sqlalchemy import select

from ..catalog import ensure_series
from ..config import get_settings
from ..db import SessionLocal
from ..logging_setup import configure_logging
from ..models import Event, Season, SourceRun, VehicleEntry
from ..services.entries import EntryStats, apply_parsed_entries
from ..services.identity import ensure_identity
from ..services.lease import LeaseLost, SyncLease
from ..services.queries import is_fixture
from ..services.sync import SyncStats, apply_parsed_sessions

log = logging.getLogger("gridline.sync")


class SuspiciousResult(RuntimeError):
    """Raised when a source result fails the safety threshold."""


@dataclass
class SyncResult:
    source_id: str
    status: str  # success | partial | failed | skipped
    stats: SyncStats | None = None
    error: str | None = None
    run_id: str | None = None
    issues: list[str] = field(default_factory=list)
    kind: str = "schedule"  # schedule | entries
    entry_stats: EntryStats | None = None


def _previous_seen(db, source_id: str, mode: str, kind: str = "schedule") -> int | None:
    return db.scalar(
        select(SourceRun.records_seen)
        .where(SourceRun.source_id == source_id, SourceRun.mode == mode, SourceRun.kind == kind,
               SourceRun.status.in_(("success", "partial")))
        .order_by(SourceRun.completed_at.desc()).limit(1)
    )


def _record_failure(db_factory, run_id, t0: float, exc: BaseException, base_log: dict, what: str) -> str:
    """Record a failed run with a fresh database session."""
    reason = f"{type(exc).__name__}: {exc}"[:2000]
    with db_factory() as db:
        failed = db.get(SourceRun, run_id)
        failed.status, failed.error = "failed", reason
        failed.completed_at = datetime.now(UTC)
        failed.duration_ms = int((time.monotonic() - t0) * 1000)
        db.commit()
        duration = failed.duration_ms
    log.error(what, extra={**base_log, "status": "failed", "failure_reason": reason, "duration_ms": duration})
    return reason


async def sync_source(
    source: MotorsportSource, *, fixtures: bool = False, db_factory=SessionLocal, now: datetime | None = None,
) -> SyncResult:
    """Sync one schedule without holding a transaction during network I/O."""
    settings = get_settings()
    mode = "fixture" if fixtures else "live"
    if not fixtures and not source.live:
        return SyncResult(source.source_id, "skipped", error=f"no live adapter. {source.limitation}")

    t0 = time.monotonic()
    with db_factory() as db:
        run = SourceRun(source_id=source.source_id, mode=mode, kind="schedule", started_at=datetime.now(UTC))
        db.add(run)
        db.commit()
        run_id = run.id
        previous = _previous_seen(db, source.source_id, mode)
        db.rollback()  # End the read transaction before network I/O.
    base_log = {"source": source.source_id, "run_id": str(run_id), "mode": mode}
    try:
        async with asyncio.timeout(settings.source_timeout_seconds):
            raw = source.load_fixture() if fixtures else await source.fetch()
            parsed = source.parse(raw)
        issues = [f"{i.event or '*'}: {i.message}" for i in parsed.issues]

        if not parsed.sessions:
            raise SuspiciousResult("parser returned zero sessions; keeping existing data")
        if previous and len(parsed.sessions) < previous * settings.sync_min_ratio:
            raise SuspiciousResult(
                f"parser returned {len(parsed.sessions)} sessions vs {previous} last run "
                f"(< {settings.sync_min_ratio:.0%}); keeping existing data"
            )

        with db_factory() as db:
            series = ensure_series(db)[source.series_slug]
            stats = apply_parsed_sessions(db, series, parsed.sessions, source_name=source.display_name(raw), now=now)
            issues += stats.warnings
            status = "partial" if issues else "success"
            run = db.get(SourceRun, run_id)
            run.status, run.records_seen, run.records_changed = status, stats.seen, stats.changed
            run.issues = len(issues)
            run.error = "; ".join(issues)[:2000] or None
            run.completed_at = datetime.now(UTC)
            run.duration_ms = int((time.monotonic() - t0) * 1000)
            db.commit()
            duration = run.duration_ms
        log.log(
            logging.WARNING if issues else logging.INFO, "source sync finished",
            extra={**base_log, "status": status, "records_seen": stats.seen, "records_changed": stats.changed,
                   "inserted": stats.inserted, "updated": stats.updated, "cancelled": stats.cancelled,
                   "issues": issues[:10], "duration_ms": duration},
        )
        return SyncResult(source.source_id, status, stats, run_id=str(run_id), issues=issues)
    except BaseException as exc:
        reason = _record_failure(db_factory, run_id, t0, exc, base_log, "source sync failed")
        if not isinstance(exc, Exception):  # KeyboardInterrupt / cancellation: record, then propagate
            raise
        return SyncResult(source.source_id, "failed", error=reason, run_id=str(run_id))


def settled_event_ids(db, series_id, now: datetime, settle_days: int) -> frozenset[str]:
    """Events that finished more than `settle_days` ago and already hold entries from a live source.
    Re-fetching them every cycle would only hammer the official site."""
    cutoff = (now - timedelta(days=settle_days)).date()
    rows = db.execute(
        select(Event.external_id, VehicleEntry.source_name)
        .join(Season, Event.season_id == Season.id).join(VehicleEntry, VehicleEntry.event_id == Event.id)
        .where(Season.series_id == series_id, Event.end_date < cutoff, VehicleEntry.source_name.is_not(None))
    )
    live = {ext for ext, name in rows if ext and not is_fixture(name)}
    return frozenset(live)


async def sync_entries(
    source: MotorsportSource, *, fixtures: bool = False, db_factory=SessionLocal, now: datetime | None = None,
) -> SyncResult | None:
    """Sync entries when the source supports them."""
    if not supports_entries(source):
        return None
    settings = get_settings()
    mode = "fixture" if fixtures else "live"
    if not fixtures and not source.live:
        return SyncResult(source.source_id, "skipped", kind="entries", error="no live adapter")
    now = now or datetime.now(UTC)

    t0 = time.monotonic()
    with db_factory() as db:
        run = SourceRun(source_id=source.source_id, mode=mode, kind="entries", started_at=datetime.now(UTC))
        db.add(run)
        db.commit()
        run_id = run.id
        base_log = {"source": source.source_id, "run_id": str(run_id), "mode": mode, "kind": "entries"}
        try:
            series = ensure_series(db)[source.series_slug]
            ensure_identity(db)
            db.commit()
            plan = EntryFetchPlan(
                settled_events=frozenset() if fixtures else settled_event_ids(db, series.id, now, settings.entries_settle_days)
            )
            db.rollback()  # End the read transaction before network I/O.
        except BaseException as exc:
            db.rollback()
            exc_a = exc
        else:
            exc_a = None
    if exc_a is not None:
        reason = _record_failure(db_factory, run_id, t0, exc_a, base_log, "entry sync failed")
        if not isinstance(exc_a, Exception):
            raise exc_a
        return SyncResult(source.source_id, "failed", error=reason, run_id=str(run_id), kind="entries")
    try:
        async with asyncio.timeout(settings.entries_timeout_seconds):
            raw = source.load_entries_fixture() if fixtures else await source.fetch_entries(plan)
            parsed = source.parse_entries(raw)
        issues = [f"{i.event or '*'}: {i.message}" for i in parsed.issues]
        if not parsed.entries and parsed.issues:
            raise SuspiciousResult("every attempted event failed to parse; keeping existing entries: " + "; ".join(issues[:3]))

        label = getattr(source, "entries_label", "entry list")
        name = f"{source.source_name} ({label}{', ' + source.fixture_label if raw.is_fixture else ''})"
        with db_factory() as db:
            series = ensure_series(db)[source.series_slug]
            stats = apply_parsed_entries(db, series, parsed.entries, source_name=name, now=now,
                                         source_id=source.source_id)
            issues += stats.warnings
            status = "partial" if issues else "success"
            run = db.get(SourceRun, run_id)
            run.status, run.records_seen, run.records_changed = status, stats.seen, stats.changed
            run.issues = len(issues)
            run.error = "; ".join(issues)[:2000] or None
            run.completed_at = datetime.now(UTC)
            run.duration_ms = int((time.monotonic() - t0) * 1000)
            db.commit()
            duration = run.duration_ms
        log.log(
            logging.WARNING if issues else logging.INFO, "entry sync finished",
            extra={**base_log, "status": status, "records_seen": stats.seen, "records_changed": stats.changed,
                   "inserted": stats.inserted, "updated": stats.updated, "removed": stats.removed,
                   "events": stats.events_applied, "issues": issues[:10], "duration_ms": duration},
        )
        return SyncResult(source.source_id, status, run_id=str(run_id), issues=issues, kind="entries", entry_stats=stats)
    except BaseException as exc:
        reason = _record_failure(db_factory, run_id, t0, exc, base_log, "entry sync failed")
        if not isinstance(exc, Exception):
            raise
        return SyncResult(source.source_id, "failed", error=reason, run_id=str(run_id), kind="entries")


async def run_sync(
    source_ids: list[str] | None = None, *, fixtures: bool = False, db_factory=SessionLocal,
) -> list[SyncResult]:
    """Run sources sequentially while holding the global sync lease."""
    if fixtures and get_settings().environment == "production":
        raise RuntimeError("fixture mode is disabled when ENVIRONMENT=production (it would relabel real data)")
    sources = [get_source(i) for i in source_ids] if source_ids else all_sources()
    results: list[SyncResult] = []

    async def work() -> None:
        for s in sources:
            results.append(await sync_source(s, fixtures=fixtures, db_factory=db_factory))
            entries = await sync_entries(s, fixtures=fixtures, db_factory=db_factory)
            if entries is not None:
                results.append(entries)

    lease = SyncLease(db_factory)
    try:
        acquired, _ = await lease.run(work)
    except LeaseLost as exc:
        log.error("sync aborted: %s", exc)
        results.append(SyncResult("lease", "failed", error=str(exc)))
        return results
    if not acquired:
        log.warning("sync skipped: another sync run holds the lease")
        return []
    if lease.release_error:
        log.warning("sync finished; lease release failed (it will expire): %s", lease.release_error)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.sources.sync")
    parser.add_argument("source", help="source id (formula1, fia_wec, imsa, gt_world_challenge) or 'all'")
    parser.add_argument("--fixtures", action="store_true", help="use bundled fixtures instead of the network")
    args = parser.parse_args(argv)
    configure_logging(get_settings().log_level)

    results = asyncio.run(run_sync(None if args.source == "all" else [args.source], fixtures=args.fixtures))
    if not results:
        print("SKIPPED  another sync is already running", file=sys.stderr)
        return 3
    failed = False
    for r in results:
        label = r.source_id if r.kind == "schedule" else f"{r.source_id}[entries]"
        if r.status in ("success", "partial") and r.stats:
            s = r.stats
            print(f"{r.status.upper():8} {label}: seen={s.seen} inserted={s.inserted} updated={s.updated} "
                  f"cancelled={s.cancelled} issues={len(r.issues)}")
        elif r.status in ("success", "partial") and r.entry_stats:
            e = r.entry_stats
            print(f"{r.status.upper():8} {label}: seen={e.seen} events={e.events_applied} inserted={e.inserted} "
                  f"updated={e.updated} removed={e.removed} issues={len(r.issues)}")
        elif r.status == "skipped":
            print(f"SKIPPED  {label}: {r.error}")
        else:
            failed = True
            print(f"FAILED   {label}: {r.error}", file=sys.stderr)
            continue
        for i in r.issues[:5]:
            print(f"           ! {i}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
