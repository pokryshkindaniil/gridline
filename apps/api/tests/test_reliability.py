"""A broken or empty upstream must never destroy valid stored schedule data."""

import datetime as dt
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from gridline_sources import ParseResult, SourceError, SourceIssue, get_source
from sqlalchemy import func, select

from app.config import get_settings
from app.models import Event, Session, SourceRun
from app.sources.sync import sync_source
from tests.conftest import TestSession
from tests.helpers import FakeSource, make_sessions


async def run(src, db):
    return await sync_source(src, db_factory=TestSession)


def count(db, **where):
    stmt = select(func.count()).select_from(Session)
    for k, v in where.items():
        stmt = stmt.where(getattr(Session, k) == v)
    return db.scalar(stmt)


async def seed(db, series, n=10, event="e1"):
    res = await run(FakeSource(ParseResult(make_sessions(n, event))), db)
    assert res.status == "success"
    db.expire_all()


async def test_empty_result_keeps_existing_data(db, series):
    await seed(db, series)
    res = await run(FakeSource(ParseResult([])), db)
    assert res.status == "failed" and "zero sessions" in res.error
    assert count(db) == 10 and count(db, status="cancelled") == 0
    assert db.scalars(select(SourceRun).order_by(SourceRun.started_at.desc())).first().status == "failed"


async def test_suspicious_drop_keeps_existing_data(db, series):
    await seed(db, series, 10)
    res = await run(FakeSource(ParseResult(make_sessions(2))), db)  # 2 < 50% of 10
    assert res.status == "failed" and "keeping existing data" in res.error
    assert count(db) == 10 and count(db, status="cancelled") == 0


async def test_moderate_shrink_is_applied_as_cancellations(db, series):
    await seed(db, series, 10)
    res = await run(FakeSource(ParseResult(make_sessions(6))), db)
    assert res.status == "success" and res.stats.cancelled == 4
    assert count(db, status="cancelled") == 4 and count(db) == 10  # cancelled, never deleted


async def test_partial_parse_failure_is_partial_and_isolated(db, series):
    await seed(db, series, 6, "e1")
    await seed(db, series, 6, "e2")
    broken = ParseResult(make_sessions(6, "e1"), [SourceIssue("e2", "SourceError: malformed page")])
    res = await run(FakeSource(broken), db)
    assert res.status == "partial" and res.issues == ["e2: SourceError: malformed page"]
    assert count(db) == 12 and count(db, status="cancelled") == 0  # e2 untouched, not cancelled
    run_row = db.scalars(select(SourceRun).order_by(SourceRun.started_at.desc())).first()
    assert run_row.status == "partial" and run_row.issues == 1 and "e2" in run_row.error


async def test_event_that_suddenly_shrinks_is_not_cancelled(db, series):
    await seed(db, series, 8, "e1")
    await seed(db, series, 8, "e2")
    shrunk = ParseResult(make_sessions(2, "e1") + make_sessions(8, "e2"))  # total 10 >= 50% of 16
    res = await run(FakeSource(shrunk), db)
    assert res.status == "partial" and any("cancellations skipped" in i for i in res.issues)
    assert count(db, status="cancelled") == 0


async def test_session_changes_start_time_in_place(db, series):
    await seed(db, series, 3)
    moved = make_sessions(3)
    moved[1] = type(moved[1])(**{**moved[1].__dict__, "start_at": moved[1].start_at + timedelta(minutes=30)})
    sid = db.scalar(select(Session.id).where(Session.external_id == "s1"))
    res = await run(FakeSource(ParseResult(moved)), db)
    assert res.stats.updated == 1 and count(db) == 3
    db.expire_all()
    assert db.get(Session, sid).sequence == 1


async def test_event_date_change_updates_event(db, series):
    await seed(db, series, 3)
    shifted = [type(s)(**{**s.__dict__, "event_start_date": s.event_start_date + timedelta(days=7),
                          "event_end_date": s.event_end_date + timedelta(days=7)}) for s in make_sessions(3)]
    await run(FakeSource(ParseResult(shifted)), db)
    db.expire_all()
    ev = db.scalar(select(Event))
    assert ev.start_date.isoformat() == "2026-11-07" and ev.end_date.isoformat() == "2026-11-09"
    assert db.scalar(select(func.count()).select_from(Event)) == 1


async def test_source_timeout_fails_run_keeps_data(db, series, monkeypatch):
    await seed(db, series)
    monkeypatch.setattr(get_settings(), "source_timeout_seconds", 0.05)
    res = await run(FakeSource(ParseResult(make_sessions(10)), delay=1.0), db)
    assert res.status == "failed" and "TimeoutError" in res.error and count(db) == 10


async def test_fetch_and_parse_exceptions_are_isolated_per_source(db, series):
    await seed(db, series)
    for bad in (FakeSource(fetch_error=SourceError("HTTP 503")), FakeSource(SourceError("unusable payload")),
                FakeSource(ValueError("boom"))):
        res = await run(bad, db)
        assert res.status == "failed"
    assert count(db) == 10 and count(db, status="cancelled") == 0


# ---- adapter-level HTTP behaviour via httpx.MockTransport (no network) -----------------------------------

def gtwc(handler):
    src = get_source("gt_world_challenge")
    src.transport, src.request_delay = httpx.MockTransport(handler), 0
    return src


def serve_gtwc_fixtures(request: httpx.Request) -> httpx.Response:
    fx = Path(get_source("gt_world_challenge").fixture_dir)
    path = request.url.path
    if path == "/calendar":
        return httpx.Response(200, text=(fx / "calendar.html").read_text())
    n = path.split("/")[2]
    return httpx.Response(200, text=(fx / f"event_{n}.html").read_text())


async def test_gtwc_adapter_fetches_and_parses_over_http():
    src = gtwc(serve_gtwc_fixtures)
    result = src.parse(await src.fetch())
    assert len(result.sessions) == 103 and result.issues == []


async def test_http_5xx_raises_source_error():
    src = gtwc(lambda r: httpx.Response(503, text="unavailable"))
    with pytest.raises(SourceError, match="503"):
        await src.fetch()


async def test_http_timeout_raises_source_error():
    def boom(request):
        raise httpx.ReadTimeout("slow", request=request)
    with pytest.raises(SourceError):
        await gtwc(boom).fetch()


async def test_empty_response_raises_source_error():
    with pytest.raises(SourceError, match="no /event/ links"):
        await gtwc(lambda r: httpx.Response(200, text="")).fetch()


async def test_one_malformed_event_page_is_an_issue_not_a_failure():
    def handler(request):
        if request.url.path.startswith("/event/254/"):
            return httpx.Response(200, text="<html><body>maintenance</body></html>")
        return serve_gtwc_fixtures(request)

    src = gtwc(handler)
    result = src.parse(await src.fetch())
    assert len(result.issues) == 1 and "JSON-LD" in result.issues[0].message
    assert len(result.sessions) > 90 and not any(s.event_external_id == "e254" for s in result.sessions)


def test_all_malformed_raises_nothing_to_parse():
    src = get_source("gt_world_challenge")
    from gridline_sources import RawSchedule
    raw = RawSchedule(src.official_url, dt.datetime.now(dt.UTC), {"/event/1/x": "<html></html>"})
    result = src.parse(raw)
    assert result.sessions == [] and len(result.issues) == 1  # sync then refuses the empty result


def test_f1_malformed_json_ld_quarantines_only_that_race():
    src = get_source("formula1")
    raw = src.load_fixture()
    docs = dict(raw.documents)
    docs["race_singapore.html"] = docs["race_singapore.html"].replace('"subEvent"', '"subEventX"')
    docs["race_japan.html"] = '<script type="application/ld+json">{not json</script>'
    from gridline_sources import RawSchedule
    result = src.parse(RawSchedule(raw.source_url, raw.fetched_at, docs, True))
    assert {i.event for i in result.issues} == {"race_singapore.html", "race_japan.html"}
    good = src.parse(raw).sessions
    dropped = {"singapore", "japan"}
    assert len(result.sessions) == len([s for s in good if s.event_external_id not in dropped])


def test_wec_malformed_ics_and_missing_calendar_are_issues():
    src = get_source("fia_wec")
    raw = src.load_fixture()
    docs = dict(raw.documents)
    docs["race_6-hours-of-fuji-2026.ics"] = "this is not a calendar"
    del docs["race_6-hours-of-imola-2026.ics"]
    from gridline_sources import RawSchedule
    result = src.parse(RawSchedule(raw.source_url, raw.fetched_at, docs, True))
    assert {i.event for i in result.issues} == {"6-hours-of-fuji-2026", "6-hours-of-imola-2026"}
    assert any(s.event_external_id == "6-hours-of-monza-2026" for s in result.sessions)
