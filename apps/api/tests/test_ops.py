"""Health semantics, scheduler behaviour, retention."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.config import Settings
from app.maintenance import cleanup_source_runs
from app.models import SessionChange, SourceRun
from app.scheduler import loop
from app.services.health import RunView, classify
from app.sources import sync as sync_mod
from tests.conftest import TestSession

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
S = Settings(source_healthy_max_age_minutes=90, source_failing_after_failures=2)


def run(status, minutes_ago, mode="live"):
    t = NOW - timedelta(minutes=minutes_ago)
    return RunView(status, mode, t, t)


def test_health_classification_matrix():
    c = lambda *runs, live=True: classify(live, list(runs), NOW, S)  # noqa: E731
    assert c(run("success", 10)) == "healthy"
    assert c(run("success", 89)) == "healthy"
    assert c(run("success", 120)) == "stale"
    assert c() == "stale"  # never synced
    assert c(run("partial", 10)) == "degraded"
    assert c(run("failed", 5), run("success", 35)) == "healthy"  # one blip while still fresh
    assert c(run("failed", 5), run("failed", 35), run("success", 65)) == "failing"  # 2 consecutive
    assert c(run("failed", 5), run("success", 300)) == "failing"  # failed and no longer fresh
    assert c(run("success", 10, "fixture")) == "stale"  # fixture runs never count as live
    assert c(run("success", 1, "fixture"), live=False) == "fixture_only"
    assert c(run("running", 1), run("success", 20)) == "healthy"


def test_thresholds_are_configurable():
    strict = Settings(source_healthy_max_age_minutes=5, source_failing_after_failures=1)
    assert classify(True, [run("success", 10)], NOW, strict) == "stale"
    assert classify(True, [run("failed", 1), run("success", 2)], NOW, strict) == "failing"


def test_health_endpoints_have_different_semantics(client, db, series):
    app_health = client.get("/health").json()
    assert app_health == {"status": "ok", "database": "up"}  # says nothing about sources
    data_health = {h["source_id"]: h for h in client.get("/sources/health").json()}
    assert data_health["formula1"]["status"] == "stale" and "imsa" not in data_health
    assert {"source_name", "last_successful_sync", "last_attempt", "records_seen", "records_changed"} <= set(data_health["formula1"])
    db.add(SourceRun(source_id="formula1", mode="live", status="success", started_at=datetime.now(UTC),
                     completed_at=datetime.now(UTC), records_seen=10, records_changed=1))
    db.commit()
    assert {h["source_id"]: h for h in client.get("/sources/health").json()}["formula1"]["status"] == "healthy"
    assert client.get("/health").json()["status"] == "ok"


def test_health_reports_503_when_database_is_down(client, monkeypatch):
    from app.routers import core

    class Broken:
        def __enter__(self):
            raise RuntimeError("db down")

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(core, "SessionLocal", lambda: Broken())
    r = client.get("/health")
    assert r.status_code == 503 and r.json()["database"] == "down"


async def test_overlapping_runs_are_prevented_by_the_sync_lease(db):
    from app.services.lease import SyncLease

    holder = SyncLease(TestSession)  # another process holding the lease
    assert holder.acquire()
    assert await sync_mod.run_sync(["imsa"], db_factory=TestSession) == []
    assert holder.release()
    results = await sync_mod.run_sync(["imsa"], db_factory=TestSession)  # lease released -> runs (skipped: no live)
    assert [r.status for r in results] == ["skipped"]


async def test_scheduler_survives_a_crashing_cycle(monkeypatch):
    calls = []

    async def boom(_ids):
        calls.append(1)
        raise RuntimeError("cycle exploded")

    monkeypatch.setattr("app.scheduler.run_sync", boom)
    await loop(once=True)  # must not raise
    assert calls == [1]


async def test_one_failing_source_does_not_stop_the_others(db, series, monkeypatch):
    from tests.helpers import FakeSource

    seen = []
    real = sync_mod.sync_source

    async def spy(source, **kw):
        seen.append(source.source_id)
        return await real(source, **kw)

    monkeypatch.setattr(sync_mod, "sync_source", spy)
    monkeypatch.setattr(sync_mod, "get_source", lambda i: FakeSource(fetch_error=RuntimeError("down")) if i == "a" else FakeSource(fetch_error=RuntimeError("down2")))
    results = await sync_mod.run_sync(["a", "b"], db_factory=TestSession)
    assert [r.status for r in results] == ["failed", "failed"] and len(seen) == 2


def test_cleanup_prunes_old_runs_but_keeps_health_anchors_and_history(db, series):
    def add(status, days_ago, source="formula1", mode="live"):
        t = NOW - timedelta(days=days_ago)
        db.add(SourceRun(source_id=source, mode=mode, status=status, started_at=t, completed_at=t))

    for d in (100, 90, 80, 40, 35, 1):
        add("failed", d)
    add("success", 95)           # old but newest success for formula1/live -> must survive
    add("success", 50, "imsa", "fixture")
    for d in (60, 10):
        add("failed", d, "fia_wec")
    db.commit()
    before = db.scalar(select(func.count()).select_from(SourceRun))
    deleted = cleanup_source_runs(30, db_factory=TestSession, now=NOW)
    db.expire_all()
    left = list(db.scalars(select(SourceRun)))
    assert deleted == before - len(left) > 0
    assert all(r.started_at >= NOW - timedelta(days=30) or r.status == "success" for r in left)
    assert any(r.status == "success" and r.source_id == "formula1" for r in left)  # newest success kept
    assert db.scalar(select(func.count()).select_from(SessionChange)) == 0  # history table untouched


async def test_fixture_mode_is_refused_in_production(monkeypatch):
    import pytest

    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "environment", "production")
    with pytest.raises(RuntimeError, match="fixture mode is disabled"):
        await sync_mod.run_sync(["imsa"], fixtures=True, db_factory=TestSession)


def test_every_route_answers_under_the_canonical_api_prefix_and_unprefixed(client):
    """Vercel forwards the original path (/api/x) to the service; local dev and Docker call /x. Both work, and
    nothing answers at /api/api/x."""
    assert client.get("/api/health").json() == client.get("/health").json()
    assert client.get("/api/series").status_code == 200 and client.get("/series").status_code == 200
    assert client.get("/api/nope").status_code == 404 and client.get("/api/api/series").status_code == 404


def test_docs_are_served_under_the_api_prefix_and_point_at_the_prefixed_schema(client):
    page = client.get("/api/docs")
    assert page.status_code == 200 and "/api/openapi.json" in page.text
    assert client.get("/api/openapi.json").status_code == 200


def test_calendar_subscription_path_is_under_the_public_api_prefix(client, db, series, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "public_api_base_url", "https://gridline.example/api")
    made = client.post("/api/feeds", json={"series": ["formula-1"], "session_types": ["race"], "timezone": "UTC"}).json()
    assert made["public_url"] == f"https://gridline.example/api/calendar/{made['public_token']}.ics"
    assert made["webcal_url"].startswith("webcal://gridline.example/api/calendar/")
    assert client.get(f"/api/calendar/{made['public_token']}.ics").status_code == 200
    assert client.get(f"/calendar/{made['public_token']}.ics").status_code == 200


def test_production_refuses_a_missing_or_local_database_url():
    import pytest as _pytest

    from app.config import Settings

    ok = dict(environment="production", cors_origins="https://g.example", public_api_base_url="https://g.example/api")
    with _pytest.raises(ValueError, match="DATABASE_URL"):
        Settings(_env_file=None, **ok)  # default local database
    with _pytest.raises(ValueError, match="psycopg"):
        Settings(_env_file=None, database_url="postgresql://u:p@ep.neon.tech/gridline", **ok)
    assert Settings(_env_file=None, database_url="postgresql+psycopg://u:p@ep.neon.tech/gridline", **ok).environment == "production"
