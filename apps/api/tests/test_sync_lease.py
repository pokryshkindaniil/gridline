"""The sync lease: atomic acquisition, heartbeat, takeover after expiry, ownership-checked release, lost-lease abort."""

from __future__ import annotations

import asyncio

import pytest
from gridline_sources import EntryParseResult, ParseResult
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.models import SourceRun
from app.services.lease import GLOBAL_SYNC, SyncLease
from app.sources import sync as sync_mod

from .conftest import TestSession, engine
from .helpers import FakeEntrySource, FakeSource, make_sessions


def row():
    with engine.connect() as c:
        return c.execute(text("select owner_token, expires_at > now() as live, expires_at from sync_leases where name = :n"),
                         {"n": GLOBAL_SYNC}).first()


def expire_now():
    """Simulate a crashed runner: its lease just stops being renewed and runs out."""
    with engine.begin() as c:
        c.execute(text("update sync_leases set expires_at = now() - interval '1 second' where name = :n"), {"n": GLOBAL_SYNC})


def lease(**kw) -> SyncLease:
    return SyncLease(TestSession, ttl=kw.pop("ttl", 30), heartbeat=kw.pop("heartbeat", 5), **kw)


def test_the_first_runner_acquires_and_a_concurrent_second_is_refused(db):
    a, b = lease(), lease()
    assert a.token != b.token                 # unique owner token per run
    assert a.acquire() is True
    assert b.acquire() is False               # live lease: refused
    assert row().owner_token == a.token and row().live


def test_acquisition_is_one_atomic_statement_many_contenders_exactly_one_wins(db):
    from concurrent.futures import ThreadPoolExecutor

    contenders = [lease() for _ in range(12)]
    with ThreadPoolExecutor(12) as pool:
        won = list(pool.map(lambda c: c.acquire(), contenders))
    assert sum(won) == 1
    assert row().owner_token == contenders[won.index(True)].token


def test_an_expired_lease_can_be_taken_over_and_the_old_owner_is_then_locked_out(db):
    a, b = lease(), lease()
    assert a.acquire()
    expire_now()                              # a "crashed": no renewal
    assert b.acquire() is True                # no manual intervention needed
    assert row().owner_token == b.token
    assert a.renew() is False                 # the old owner can no longer renew
    assert a.release() is False               # nor release the new owner's lease
    assert row().owner_token == b.token and row().live


def test_heartbeat_extends_the_lease(db):
    a = lease(ttl=30, heartbeat=5)
    assert a.acquire()
    with engine.begin() as c:
        c.execute(text("update sync_leases set expires_at = now() + interval '3 seconds'"))
    before = row().expires_at
    assert a.renew() is True
    assert row().expires_at > before and row().live


def test_a_wrong_owner_cannot_heartbeat_or_release(db):
    a, intruder = lease(), lease()
    assert a.acquire()
    assert intruder.renew() is False and intruder.release() is False
    assert row().owner_token == a.token


def test_release_deletes_only_our_row_and_makes_it_acquirable(db):
    a, b = lease(), lease()
    assert a.acquire() and a.release() and row() is None
    assert b.acquire()


def test_ttl_must_be_comfortably_above_the_heartbeat():
    with pytest.raises(ValueError):
        SyncLease(TestSession, ttl=10, heartbeat=5)


# ---------------------------------------------------------------------------------------------- run_sync integration

def patch_sources(monkeypatch, *sources):
    monkeypatch.setattr(sync_mod, "get_source", lambda _id: sources[0])
    monkeypatch.setattr(sync_mod, "all_sources", lambda: list(sources))


async def test_the_lease_is_released_after_success_and_after_a_source_failure(db, series, monkeypatch):
    for src in (FakeSource(ParseResult(make_sessions(2))), FakeSource(fetch_error=RuntimeError("boom"))):
        patch_sources(monkeypatch, src)
        results = await sync_mod.run_sync(["x"], db_factory=TestSession)
        assert results[0].status in ("success", "failed")
        assert row() is None, "lease leaked"


async def test_a_second_sync_is_refused_while_one_runs_and_does_not_disturb_the_first(db, series, monkeypatch):
    src = FakeSource(ParseResult(make_sessions(2)))
    patch_sources(monkeypatch, src)
    inner: list = []
    real = src.fetch

    async def fetch_and_try_a_second_run():
        mine = row().owner_token
        inner.append(await sync_mod.run_sync(["x"], db_factory=TestSession))
        assert row().owner_token == mine      # the refused runner neither stole nor released it
        return await real()

    src.fetch = fetch_and_try_a_second_run
    results = await sync_mod.run_sync(["x"], db_factory=TestSession)
    assert inner == [[]] and results[0].status == "success" and row() is None


async def test_a_crashed_runner_is_recovered_by_expiry_alone(db, series, monkeypatch):
    crashed = lease()
    assert crashed.acquire()                  # a process that died holding the lease
    patch_sources(monkeypatch, FakeSource(ParseResult(make_sessions(2))))
    assert await sync_mod.run_sync(["x"], db_factory=TestSession) == []   # still live: refused
    expire_now()
    results = await sync_mod.run_sync(["x"], db_factory=TestSession)      # takes over by itself
    assert results and results[0].status == "success" and row() is None


async def test_heartbeats_keep_a_long_run_alive_using_short_transactions_only(db, series, monkeypatch):
    class Slow(FakeSource):
        async def fetch(self):
            await asyncio.sleep(0.5)          # several heartbeats happen meanwhile
            from .test_sync_lifecycle import checked_out, idle_in_transaction
            self.seen = (idle_in_transaction(), checked_out())
            return await super().fetch()

    src = Slow(ParseResult(make_sessions(2)))
    patch_sources(monkeypatch, src)
    beats = []
    real = SyncLease.renew

    def counting(self):
        beats.append(1)
        return real(self)

    monkeypatch.setattr(SyncLease, "renew", counting)
    monkeypatch.setattr(sync_mod, "SyncLease", lambda f: SyncLease(f, ttl=3, heartbeat=0.1))
    results = await sync_mod.run_sync(["x"], db_factory=TestSession)
    assert results[0].status == "success" and len(beats) >= 3
    assert src.seen == (0, 0)                 # no open transaction, no borrowed connection while "on the network"


async def test_a_transient_heartbeat_failure_is_retried_and_the_run_completes(db, series, monkeypatch):
    class Slow(FakeSource):
        async def fetch(self):
            await asyncio.sleep(0.5)
            return await super().fetch()

    patch_sources(monkeypatch, Slow(ParseResult(make_sessions(2))))
    real, calls = SyncLease.renew, []

    def flaky(self):
        calls.append(1)
        if len(calls) == 1:
            raise OperationalError("select", {}, Exception("connection terminated"))
        return real(self)

    monkeypatch.setattr(SyncLease, "renew", flaky)
    monkeypatch.setattr(sync_mod, "SyncLease", lambda f: SyncLease(f, ttl=3, heartbeat=0.1, max_failures=3))
    results = await sync_mod.run_sync(["x"], db_factory=TestSession)
    assert results[0].status == "success" and len(calls) >= 2 and row() is None


async def test_persistent_heartbeat_failure_loses_the_lease_and_aborts_the_run(db, series, monkeypatch):
    started = []

    class Slow(FakeSource):
        async def fetch(self):
            started.append(1)
            await asyncio.sleep(5)            # would run "forever" if nobody noticed the lost lease
            return await super().fetch()

    patch_sources(monkeypatch, Slow(ParseResult(make_sessions(2))))

    def dead(self):
        raise OperationalError("select", {}, Exception("terminating connection due to administrator command"))

    monkeypatch.setattr(SyncLease, "renew", dead)
    monkeypatch.setattr(sync_mod, "SyncLease", lambda f: SyncLease(f, ttl=3, heartbeat=0.05, max_failures=3))
    results = await asyncio.wait_for(sync_mod.run_sync(["x"], db_factory=TestSession), timeout=3)
    assert started == [1]
    assert [r.status for r in results] == ["failed"]               # the lease failure (the cancelled source returns nothing)
    assert results[-1].source_id == "lease" and "lost" in results[-1].error
    with engine.connect() as c:               # the interrupted run is recorded, not left 'running'
        assert c.execute(text("select status from source_runs order by started_at desc limit 1")).scalar() == "failed"


async def test_losing_ownership_to_another_runner_aborts_without_touching_their_lease(db, series, monkeypatch):
    class Slow(FakeSource):
        async def fetch(self):
            expire_now()                      # our lease runs out …
            thief = lease()
            assert thief.acquire()            # … and another runner takes over
            self.thief = thief
            await asyncio.sleep(5)
            return await super().fetch()

    src = Slow(ParseResult(make_sessions(2)))
    patch_sources(monkeypatch, src)
    monkeypatch.setattr(sync_mod, "SyncLease", lambda f: SyncLease(f, ttl=3, heartbeat=0.05))
    results = await asyncio.wait_for(sync_mod.run_sync(["x"], db_factory=TestSession), timeout=3)
    assert results[-1].source_id == "lease" and results[-1].status == "failed"
    assert row().owner_token == src.thief.token     # the new owner's lease survived our release attempt


async def test_a_failing_release_after_complete_work_does_not_fail_the_sync_and_the_ttl_recovers(db, series, monkeypatch):
    patch_sources(monkeypatch, FakeSource(ParseResult(make_sessions(2))))

    def broken_release(self):
        raise OperationalError("delete", {}, Exception("connection terminated"))

    monkeypatch.setattr(SyncLease, "release", broken_release)
    results = await sync_mod.run_sync(["x"], db_factory=TestSession)
    assert results[0].status == "success"            # the data sync itself succeeded and is reported as such
    assert row() is not None                          # lease still there …
    expire_now()
    monkeypatch.undo()
    assert lease().acquire()                          # … and expiry makes it acquirable again


async def test_cancellation_that_is_not_a_lost_lease_still_propagates_and_releases(db, series, monkeypatch):
    class Hang(FakeSource):
        async def fetch(self):
            await asyncio.sleep(5)

    patch_sources(monkeypatch, Hang(ParseResult(make_sessions(2))))
    task = asyncio.ensure_future(sync_mod.run_sync(["x"], db_factory=TestSession))
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert row() is None


async def test_source_isolation_and_source_runs_are_unchanged_under_the_lease(db, series, monkeypatch):
    a, b = FakeSource(fetch_error=RuntimeError("down")), FakeSource(ParseResult(make_sessions(2)))
    monkeypatch.setattr(sync_mod, "get_source", lambda i: {"a": a, "b": b}[i])
    results = await sync_mod.run_sync(["a", "b"], db_factory=TestSession)
    assert [r.status for r in results] == ["failed", "success"]
    assert db.query(SourceRun).count() == 2
    _ = EntryParseResult, FakeEntrySource
