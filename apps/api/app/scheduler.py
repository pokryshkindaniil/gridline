"""Simple scheduler: run `sync all` every SYNC_INTERVAL_MINUTES, plus daily SourceRun cleanup.

    python -m app.scheduler            # loop forever
    python -m app.scheduler --once     # single pass (cron-compatible)

No Celery/Redis: a plain loop. Overlap protection is the database sync lease in run_sync(), so even
two scheduler containers cannot run syncs concurrently.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import time

from .config import get_settings
from .logging_setup import configure_logging
from .maintenance import cleanup_source_runs
from .sources.sync import run_sync

log = logging.getLogger("gridline.scheduler")
CLEANUP_EVERY_SECONDS = 24 * 3600


async def tick(last_cleanup: float) -> float:
    started = time.monotonic()
    results = await run_sync(None)
    log.info("sync cycle complete", extra={
        "sources": {f"{r.source_id}:{r.kind}": r.status for r in results},
        "duration_ms": int((time.monotonic() - started) * 1000),
    })
    if time.time() - last_cleanup > CLEANUP_EVERY_SECONDS:
        deleted = cleanup_source_runs(get_settings().source_run_retention_days)
        log.info("source run cleanup", extra={"deleted": deleted})
        return time.time()
    return last_cleanup


async def loop(once: bool) -> None:
    settings = get_settings()
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(sig, stop.set)
    interval = settings.sync_interval_minutes * 60
    last_cleanup = 0.0
    log.info("scheduler started", extra={"interval_minutes": settings.sync_interval_minutes})
    while not stop.is_set():
        try:
            last_cleanup = await tick(last_cleanup)
        except Exception:  # a failing cycle must never kill the scheduler
            log.exception("sync cycle crashed")
        if once:
            return
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            pass
    log.info("scheduler stopped")


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.scheduler")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    configure_logging(get_settings().log_level)
    asyncio.run(loop(args.once))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
