from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://gridline:gridline@localhost:5432/gridline_test")
os.environ["DATABASE_URL"] = TEST_DB_URL  # before app modules read settings

from datetime import UTC, datetime  # noqa: E402

from gridline_sources import get_source  # noqa: E402

from app.catalog import ensure_series  # noqa: E402
from app.db import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, SourceRun  # noqa: E402
from app.services.sync import apply_parsed_sessions  # noqa: E402

FIXTURE_NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)

engine = create_engine(TEST_DB_URL, connect_args={"options": "-c timezone=UTC"})
TestSession = sessionmaker(engine, expire_on_commit=False)


@pytest.fixture(scope="session")
def _schema() -> Iterator[None]:
    with engine.begin() as conn:  # clean slate, even if an older schema is left over
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def db(_schema) -> Iterator[Session]:
    with TestSession() as s:
        yield s
    with engine.begin() as conn:
        names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))


@pytest.fixture
def series(db: Session):
    s = ensure_series(db)
    db.commit()
    return s


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: (yield db)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    from app.ratelimit import limiter

    limiter.reset()


@pytest.fixture
def seeded(db: Session, series):
    """Every adapter's fixture schedule through the real sync engine (IMSA included: it is hidden, not deleted)."""
    for sid in ("formula1", "gt_world_challenge", "fia_wec", "imsa"):
        src = get_source(sid)
        raw = src.load_fixture()
        apply_parsed_sessions(db, series[src.series_slug], src.parse(raw).sessions, source_name=src.display_name(raw), now=FIXTURE_NOW)
        db.add(SourceRun(source_id=sid, mode="fixture", status="success", started_at=FIXTURE_NOW, completed_at=FIXTURE_NOW,
                         records_seen=1, records_changed=1))
    db.commit()
