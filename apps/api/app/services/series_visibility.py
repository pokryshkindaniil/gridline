"""The one source of truth for "may this series appear in the public product".

`Series.public` is set in `app.catalog.SERIES_CATALOG` (never in a router, component or query by slug). A series that
is not public keeps its adapter, fixtures, tests and stored data, but:

  - it is absent from /series, /events, /sessions, /weekend and every feed;
  - it cannot be selected into a feed (create or update) — `require_public` rejects it;
  - its teams, entry lists and source-health rows are not served.

Every public query goes through `public_only()` / `require_public()` so a new endpoint has one obvious thing to call.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import ColumnElement, select
from sqlalchemy.orm import Session as Db

from ..models import Series


def public_only() -> ColumnElement[bool]:
    return Series.public.is_(True)


def public_series_slugs(db: Db) -> set[str]:
    return set(db.scalars(select(Series.slug).where(public_only())))


def filter_public(series: Iterable[Series]) -> list[Series]:
    return [s for s in series if s.public]
