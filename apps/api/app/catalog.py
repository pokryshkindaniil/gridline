"""Series catalogue: which championships GRIDLINE knows about.

`active` = has a sync adapter. `public` = part of the public product. They are independent and BOTH explicit on every
entry (never inferred from each other): a series without a supported source must say `public=False`.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .models import Series

SERIES_CATALOG = [
    dict(slug="formula-1", name="Formula 1", short_name="F1", category="formula",
         official_url="https://www.formula1.com", active=True, public=True),
    dict(slug="fia-wec", name="FIA World Endurance Championship", short_name="WEC", category="endurance",
         official_url="https://www.fiawec.com", active=True, public=True),
    dict(slug="imsa-weathertech", name="IMSA WeatherTech SportsCar Championship", short_name="IMSA",
         category="endurance", official_url="https://www.imsa.com", active=True,
         public=False),  # fixture-only: no source we may ingest and redistribute automatically yet
    dict(slug="gt-world-challenge-europe", name="GT World Challenge Europe", short_name="GTWC",
         category="gt", official_url="https://www.gt-world-challenge-europe.com", active=True, public=True),
    dict(slug="wrc", name="World Rally Championship", short_name="WRC", category="rally",
         official_url="https://www.wrc.com", active=False, public=False),
    dict(slug="formula-e", name="ABB FIA Formula E", short_name="FE", category="formula",
         official_url="https://www.fiaformulae.com", active=False, public=False),
    dict(slug="motogp", name="MotoGP", short_name="MotoGP", category="moto",
         official_url="https://www.motogp.com", active=False, public=False),
]


def ensure_series(db: DbSession) -> dict[str, Series]:
    existing = {s.slug: s for s in db.scalars(select(Series))}
    for row in SERIES_CATALOG:
        s = existing.get(row["slug"])
        if s is None:
            s = Series(**row)
            db.add(s)
            existing[row["slug"]] = s
        else:
            for k, v in row.items():
                setattr(s, k, v)
    db.flush()
    return existing
