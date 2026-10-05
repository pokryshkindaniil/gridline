"""Transaction lifecycle of a sync run: no transaction is open during network IO, and the global lock is a
dedicated AUTOCOMMIT connection. Regression for Neon's `idle-in-transaction session timeout` killing a WEC entries
run whose fetch took ~9 minutes."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from gridline_sources import EntryParseResult, ParseResult
from sqlalchemy import select, text

from app.models import SourceRun
from app.sources import sync as sync_mod

from .conftest import TestSession, engine
from .helpers import FakeEntrySource, FakeSource, make_sessions

IDLE_IN_TXN = """select count(*) from pg_stat_activity
                 where datname = current_database() and pid <> pg_backend_pid() and state like 'idle in transaction%'"""


def idle_in_transaction() -> int:
    with engine.connect() as c:
        return c.execute(text(IDLE_IN_TXN)).scalar()


def checked_out() -> int:
    """Connections currently borrowed from the application pool (0 = no persistent DB connection)."""
    return engine.pool.checkedout()


def lease_row():
    with engine.connect() as c:
        return c.execute(text("select name, owner_token from sync_leases")).first()


class Probe(FakeEntrySource):
    """Records what the database looks like while the 'network' is being used."""

    def __init__(self, **kw) -> None:
        super().__init__(EntryParseResult([]), **kw)
        self.result = ParseResult(make_sessions(2))
        self.during: dict[str, list] = {"fetch": [], "fetch_entries": []}

    async def fetch(self):
        self.during["fetch"].append((idle_in_transaction(), checked_out()))
        return await super().fetch()

    async def fetch_entries(self, plan):
        self.during["fetch_entries"].append((idle_in_transaction(), checked_out()))
        return await super().fetch_entries(plan)


@pytest.fixture
def probe(series, monkeypatch):
    monkeypatch.setattr(sync_mod, "supports_entries", lambda s: True)
    return Probe()


async def test_no_transaction_is_open_while_the_schedule_is_fetched(db, series):
    src = Probe()
    r = await sync_mod.sync_source(src, db_factory=TestSession)
    assert r.status == "success"
    assert src.during["fetch"] == [(0, 0)]  # nothing idle in a transaction and no pooled connection borrowed


async def test_no_transaction_is_open_while_entries_are_fetched_even_after_the_plan_queries(db, series):
    """The fetch plan is built from database SELECTs (settled events). Those must be finished, not left open."""
    src = Probe()
    r = await sync_mod.sync_entries(src, db_factory=TestSession)
    assert r.status == "success" and r.kind == "entries"
    assert src.during["fetch_entries"] == [(0, 0)]
    assert len(src.plans) == 1


async def test_whole_run_with_the_lease_held_never_idles_in_a_transaction_or_holds_a_connection(db, series, monkeypatch):
    src = Probe()
    monkeypatch.setattr(sync_mod, "get_source", lambda _id: src)
    monkeypatch.setattr(sync_mod, "all_sources", lambda: [src])
    results = await sync_mod.run_sync(["x"], db_factory=TestSession)
    assert [(r.kind, r.status) for r in results] == [("schedule", "success"), ("entries", "success")]
    # while the lease is held and the network is used: no open transaction and NO borrowed connection at all
    assert src.during["fetch"] == [(0, 0)] and src.during["fetch_entries"] == [(0, 0)]
    assert lease_row() is None  # released at the end


async def test_a_failed_fetch_is_recorded_from_a_fresh_session_with_nothing_left_open(db, series):
    src = FakeEntrySource(fetch_error=RuntimeError("upstream down"))
    r = await sync_mod.sync_entries(src, db_factory=TestSession)
    assert r.status == "failed" and "upstream down" in r.error
    assert idle_in_transaction() == 0
    run = db.scalar(select(SourceRun).where(SourceRun.kind == "entries"))
    assert run.status == "failed" and "upstream down" in run.error and run.completed_at is not None


async def test_a_failure_while_applying_is_recorded_too(db, series, monkeypatch):
    src = FakeEntrySource(EntryParseResult([]))
    monkeypatch.setattr(sync_mod, "apply_parsed_entries", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("write failed")))
    r = await sync_mod.sync_entries(src, db_factory=TestSession)
    assert r.status == "failed" and "write failed" in r.error
    assert idle_in_transaction() == 0
    assert db.scalar(select(SourceRun.status).where(SourceRun.kind == "entries")) == "failed"


async def test_a_failure_while_building_the_plan_is_recorded(db, series, monkeypatch):
    monkeypatch.setattr(sync_mod, "settled_event_ids", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("plan failed")))
    r = await sync_mod.sync_entries(FakeEntrySource(EntryParseResult([])), db_factory=TestSession)
    assert r.status == "failed" and "plan failed" in r.error


async def test_schedule_safety_checks_still_protect_stored_data(db, series):
    ok = FakeSource(ParseResult(make_sessions(10)))
    assert (await sync_mod.sync_source(ok, db_factory=TestSession)).status == "success"
    shrunk = FakeSource(ParseResult(make_sessions(2)))                     # < 50% of the previous run
    r = await sync_mod.sync_source(shrunk, db_factory=TestSession)
    assert r.status == "failed" and "keeping existing data" in r.error
    empty = await sync_mod.sync_source(FakeSource(ParseResult([])), db_factory=TestSession)
    assert empty.status == "failed"
    assert idle_in_transaction() == 0
    assert db.scalar(select(SourceRun.status).order_by(SourceRun.started_at.desc()).limit(1)) == "failed"
    _ = datetime.now(UTC)
