from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SeriesOut(ORM):
    slug: str
    name: str
    short_name: str
    category: str
    official_url: str
    logo_url: str | None = None
    active: bool


class EventOut(ORM):
    id: uuid.UUID
    slug: str
    name: str
    series_slug: str
    series_short_name: str
    year: int
    circuit_name: str | None = None
    city: str | None = None
    country_code: str | None = None
    timezone: str
    start_date: date
    end_date: date
    official_url: str | None = None
    status: str


class SessionEventRef(ORM):
    id: uuid.UUID
    slug: str
    name: str
    circuit_name: str | None = None
    country_code: str | None = None
    timezone: str


class SessionOut(ORM):
    id: uuid.UUID
    event: SessionEventRef
    series: SeriesOut
    name: str
    session_type: str
    start_at: datetime
    end_at: datetime | None = None
    status: str
    source_url: str
    source_name: str
    source_updated_at: datetime | None = None
    checked_at: datetime
    is_fixture: bool  # derived: source_name marks fixture data (not live)


class SeriesDetail(SeriesOut):
    next_event: EventOut | None = None
    next_session: SessionOut | None = None
    season_year: int | None = None  # the season shown: current one with events
    event_count: int = 0  # events in that season


class WeekendOut(BaseModel):
    start_date: date
    end_date: date
    timezone: str
    session_count: int
    series_count: int
    sessions: list[SessionOut]


class DriverOut(ORM):
    slug: str  # canonical driver identity; a future /drivers/{slug} route
    first_name: str
    last_name: str
    nationality_code: str | None = None
    image_url: str | None = None


class VehicleOut(ORM):
    """The car of an entry. `manufacturer` and `model` are CANONICAL names (Ferrari / SF-26); the slugs identify the
    Manufacturer and VehicleModel entities (a future /cars/{slug} route). Missing model => `model` is null and
    clients show the manufacturer only."""

    manufacturer: str | None = None
    manufacturer_slug: str | None = None
    model: str | None = None
    model_slug: str | None = None  # unique per manufacturer, not globally: address a car as {manufacturer_slug}/{model_slug}
    class_name: str | None = None
    race_number: str | None = None
    image_url: str | None = None
    fallback_logo_url: str | None = None


class EntryOut(BaseModel):
    race_number: str | None
    vehicle: VehicleOut | None = None
    drivers: list[DriverOut]


class TeamOut(BaseModel):
    slug: str  # unique within a series; a future /teams/{slug} route needs ?series= until teams are cross-series
    name: str  # canonical team name
    short_name: str | None = None
    logo_url: str | None = None
    website_url: str | None = None
    series: SeriesOut
    vehicle: VehicleOut | None = None
    entries: list[EntryOut]
    # provenance of the newest entry shown; all None for hand-made development seed rows
    source_name: str | None = None
    source_url: str | None = None
    checked_at: datetime | None = None
    is_fixture: bool = False


class TeamDetail(TeamOut):
    upcoming_events: list[EventOut]
    event: EventOut | None = None  # the event whose entry list is shown (None: season-wide roster)


class EntryEventOut(BaseModel):
    """An event that has an entry list, with the provenance of that list."""

    event: EventOut
    competition: str | None = None
    entry_count: int
    driver_count: int
    source_name: str | None = None
    source_url: str | None = None
    checked_at: datetime | None = None
    is_fixture: bool
    is_default: bool  # the event shown when none is requested


class FeedIn(BaseModel):
    series: list[str] = Field(min_length=1, description="series slugs")
    session_types: list[str] = Field(min_length=1)
    timezone: str = "UTC"


class FeedPatch(BaseModel):
    series: list[str] | None = Field(default=None, min_length=1)
    session_types: list[str] | None = Field(default=None, min_length=1)
    timezone: str | None = None


class FeedOut(BaseModel):
    public_token: str
    public_url: str
    webcal_url: str
    series: list[SeriesOut]
    session_types: list[str]
    timezone: str
    created_at: datetime
    updated_at: datetime


class FeedCreated(BaseModel):
    public_url: str
    webcal_url: str
    edit_url: str  # path on the web app: /manage/{token}?token=SECRET
    public_token: str
    edit_token: str  # shown once; only its hash is stored


class ChangeOut(BaseModel):
    detected_at: datetime
    session_id: uuid.UUID
    series_short_name: str
    event_name: str
    session_name: str
    field_name: str
    old_value: str | None
    new_value: str | None
    source_url: str


class EntriesHealthOut(BaseModel):
    status: str  # healthy | degraded | stale | failing
    last_successful_sync: datetime | None
    last_attempt: datetime | None
    records_seen: int | None
    records_changed: int | None
    last_error: str | None = None
    limitation: str | None = None


class SourceHealthOut(BaseModel):
    source_id: str
    series: str
    source_name: str
    official_url: str
    live: bool
    status: str  # healthy | degraded | stale | failing | fixture_only
    last_successful_sync: datetime | None
    last_attempt: datetime | None
    records_seen: int | None
    records_changed: int | None
    last_error: str | None = None
    limitation: str | None = None
    entries: EntriesHealthOut | None = None  # only for sources with an entry-list capability
