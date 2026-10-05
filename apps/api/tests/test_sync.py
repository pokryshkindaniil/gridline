from dataclasses import replace
from datetime import UTC, datetime, timedelta

from gridline_sources import get_source
from sqlalchemy import func, select

from app.models import Session, SessionChange, SourceRun
from app.services.sync import apply_parsed_sessions
from app.sources.sync import sync_source
from tests.conftest import TestSession

T0 = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def _gtwc():
    s = get_source("gt_world_challenge")
    return s, [p for p in s.parse(s.load_fixture()).sessions if p.event_external_id == "e254"]


def _sync(db, series, parsed, now):
    return apply_parsed_sessions(db, series["gt-world-challenge-europe"], parsed, source_name="GTWC", now=now)


def test_initial_insert_then_idempotent_resync(db, series):
    _, parsed = _gtwc()
    st = _sync(db, series, parsed, T0)
    db.commit()
    assert st.inserted == len(parsed) and st.updated == 0
    st2 = _sync(db, series, parsed, T0 + timedelta(minutes=10))
    db.commit()
    assert st2.changed == 0
    assert db.scalar(select(func.count()).select_from(Session)) == len(parsed)
    assert db.scalar(select(func.count()).select_from(SessionChange)) == 0
    # freshness still advances even with no schedule change
    assert {s.checked_at for s in db.scalars(select(Session))} == {T0 + timedelta(minutes=10)}


def test_reschedule_updates_in_place_and_records_change(db, series):
    _, parsed = _gtwc()
    _sync(db, series, parsed, T0)
    db.commit()
    race = db.scalar(select(Session).where(Session.external_id == "race-1"))
    rid, old_start = race.id, race.start_at

    moved = [replace(p, start_at=p.start_at + timedelta(minutes=30)) if p.external_id == "race-1" else p for p in parsed]
    now = T0 + timedelta(hours=1)
    st = _sync(db, series, moved, now)
    db.commit()

    assert st.updated == 1 and st.inserted == 0
    assert db.scalar(select(func.count()).select_from(Session)) == len(parsed)  # no duplicate
    race = db.scalar(select(Session).where(Session.external_id == "race-1"))
    assert race.id == rid  # same id => same ICS UID
    assert race.start_at == old_start + timedelta(minutes=30)
    assert race.sequence == 1 and race.updated_at == now and race.checked_at == now
    change = db.scalar(select(SessionChange))
    assert (change.session_id, change.field_name) == (rid, "start_at")
    assert change.old_value == old_start.isoformat() and change.new_value == race.start_at.isoformat()


def test_session_missing_from_source_is_cancelled_not_deleted(db, series):
    _, parsed = _gtwc()
    _sync(db, series, parsed, T0)
    db.commit()
    st = _sync(db, series, [p for p in parsed if p.external_id != "race-2"], T0 + timedelta(hours=1))
    db.commit()
    race2 = db.scalar(select(Session).where(Session.external_id == "race-2"))
    assert st.cancelled == 1 and race2.status == "cancelled" and race2.sequence == 1
    ch = db.scalar(select(SessionChange).where(SessionChange.session_id == race2.id))
    assert (ch.field_name, ch.old_value, ch.new_value) == ("status", "scheduled", "cancelled")


def test_duplicate_upstream_records_collapse_without_phantoms(db, series):
    _, parsed = _gtwc()
    conflicting = replace(parsed[0], start_at=parsed[0].start_at + timedelta(hours=1))
    st = _sync(db, series, parsed + [parsed[0], conflicting], T0)
    db.commit()
    assert db.scalar(select(func.count()).select_from(Session)) == len(parsed)
    assert st.inserted == len(parsed) and any("conflicting duplicate" in w for w in st.warnings)


class _Broken:
    source_id, series_slug, live = "gt_world_challenge", "gt-world-challenge-europe", True
    limitation = None

    async def fetch(self):
        raise RuntimeError("upstream exploded")


async def test_failed_sync_is_recorded_not_swallowed(db, series):
    res = await sync_source(_Broken(), db_factory=TestSession)
    assert res.status == "failed" and "upstream exploded" in res.error
    run = db.scalar(select(SourceRun))
    assert run.status == "failed" and "upstream exploded" in run.error


async def test_non_live_source_is_skipped_not_faked(db, series):
    res = await sync_source(get_source("imsa"), db_factory=TestSession)
    assert res.status == "skipped"
    assert db.scalar(select(func.count()).select_from(SourceRun)) == 0
