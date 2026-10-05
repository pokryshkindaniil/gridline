"""Database-backed lease for exclusive sync runs."""

from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import datetime, timedelta

from sqlalchemy import text

from ..config import get_settings

log = logging.getLogger("gridline.lease")
GLOBAL_SYNC = "global-sync"

_ACQUIRE = text("""
    INSERT INTO sync_leases (name, owner_token, acquired_at, heartbeat_at, expires_at)
    VALUES (:name, :token, now(), now(), now() + make_interval(secs => :ttl))
    ON CONFLICT (name) DO UPDATE
       SET owner_token = EXCLUDED.owner_token, acquired_at = EXCLUDED.acquired_at,
           heartbeat_at = EXCLUDED.heartbeat_at, expires_at = EXCLUDED.expires_at
     WHERE sync_leases.expires_at < now()
    RETURNING expires_at
""")
_RENEW = text("""
    UPDATE sync_leases SET heartbeat_at = now(), expires_at = now() + make_interval(secs => :ttl)
     WHERE name = :name AND owner_token = :token
""")
_RELEASE = text("DELETE FROM sync_leases WHERE name = :name AND owner_token = :token")


class LeaseLost(RuntimeError):
    """This run no longer holds the lease; it must stop doing source work."""


class SyncLease:
    def __init__(self, db_factory, name: str = GLOBAL_SYNC, *, ttl: float | None = None,
                 heartbeat: float | None = None, max_failures: int | None = None) -> None:
        s = get_settings()
        self.db_factory, self.name = db_factory, name
        self.ttl = ttl if ttl is not None else s.sync_lease_ttl_seconds
        self.heartbeat = heartbeat if heartbeat is not None else s.sync_lease_heartbeat_seconds
        self.max_failures = max_failures if max_failures is not None else s.sync_lease_max_heartbeat_failures
        if self.ttl < 3 * self.heartbeat:
            raise ValueError("lease TTL must be at least 3x the heartbeat interval")
        self.token = secrets.token_hex(16)  # unique per run
        self.lost = False
        self.release_error: str | None = None
        self._task: asyncio.Task | None = None

    def acquire(self) -> bool:
        with self.db_factory() as db:
            row = db.execute(_ACQUIRE, {"name": self.name, "token": self.token, "ttl": self.ttl}).first()
            db.commit()
        return row is not None

    def renew(self) -> bool:
        """True if we still own the lease (and extended it); False if ownership is gone. DB errors propagate."""
        with self.db_factory() as db:
            n = db.execute(_RENEW, {"name": self.name, "token": self.token, "ttl": self.ttl}).rowcount
            db.commit()
        return n == 1

    def release(self) -> bool:
        with self.db_factory() as db:
            n = db.execute(_RELEASE, {"name": self.name, "token": self.token}).rowcount
            db.commit()
        return n == 1

    async def _beat(self, work: asyncio.Task) -> None:
        failures = 0
        while True:
            await asyncio.sleep(self.heartbeat)
            try:
                ok = await asyncio.to_thread(self.renew)
            except Exception as exc:  # noqa: BLE001 - a flaky connection is retried, not fatal on its own
                failures += 1
                log.warning("sync lease heartbeat failed", extra={"attempt": failures, "error": f"{type(exc).__name__}: {exc}"[:300]})
                if failures < self.max_failures:
                    continue
                ok = False
            else:
                if ok:
                    failures = 0
                    continue
            self.lost = True
            log.error("sync lease lost: aborting the run", extra={"lease": self.name})
            work.cancel()
            return

    async def run(self, make_work):
        """Run a coroutine while holding the lease."""
        if not await asyncio.to_thread(self.acquire):
            return False, None
        work = asyncio.ensure_future(make_work())
        self._task = asyncio.ensure_future(self._beat(work))
        try:
            try:
                return True, await work
            except asyncio.CancelledError:
                if self.lost:
                    raise LeaseLost(f"lease {self.name!r} was lost during the sync") from None
                raise
        finally:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            try:
                if not await asyncio.to_thread(self.release):
                    log.warning("sync lease was not ours at release time", extra={"lease": self.name})
            except Exception as exc:  # noqa: BLE001
                self.release_error = f"{type(exc).__name__}: {exc}"[:300]
                log.error("sync lease release failed; it expires by itself", extra={"lease": self.name, "error": self.release_error,
                                                                                    "ttl_seconds": self.ttl})


def expires_in(db_factory, name: str = GLOBAL_SYNC) -> timedelta | None:
    """Return the remaining lease duration, if the lease exists."""
    with db_factory() as db:
        v = db.execute(text("select expires_at - now() from sync_leases where name = :n"), {"n": name}).scalar()
    return v


def now_utc(db_factory) -> datetime:
    with db_factory() as db:
        return db.execute(text("select now()")).scalar()
