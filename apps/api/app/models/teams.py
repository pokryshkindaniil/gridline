from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, utc_col, uuid_pk
from .catalog import Event, Season, Series  # noqa: F401
from .identity import DriverAlias, Manufacturer, TeamAlias, VehicleModel


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("series_id", "slug"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    series_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"))
    slug: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(200))
    short_name: Mapped[str | None] = mapped_column(String(60))
    logo_url: Mapped[str | None] = mapped_column(String(500))
    website_url: Mapped[str | None] = mapped_column(String(500))
    series: Mapped[Series] = relationship()
    aliases: Mapped[list[TeamAlias]] = relationship(back_populates="team", cascade="all, delete-orphan")


class VehicleEntry(Base):
    """One car on the grid for a team in a season (event_id NULL), or an event-specific override.

    F1:        team Ferrari -> entries #44 and #16 (same model, one driver each).
    Endurance: team Ferrari AF Corse -> entries #50 and #51 (2-4 drivers each).
    An entry with event_id set replaces the season-wide entry with the same race_number for that event
    (substitute drivers, one-off number changes).

    Entries written by an official entry-list sync always have event_id set and carry provenance
    (source_name / source_url / checked_at). An event that has such entries is described completely by them:
    season-wide (seed) rows are not mixed in.
    """

    __tablename__ = "vehicle_entries"
    __table_args__ = (
        Index("uq_vehicle_entries_season_number", "team_id", "season_id", "race_number", unique=True,
              postgresql_where=text("event_id IS NULL")),
        Index("uq_vehicle_entries_event_number", "team_id", "season_id", "event_id", "race_number", unique=True,
              postgresql_where=text("event_id IS NOT NULL")),
        Index("ix_vehicle_entries_season_id_team_id", "season_id", "team_id"),
        Index("ix_vehicle_entries_event_id", "event_id"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    season_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"))
    event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    race_number: Mapped[str | None] = mapped_column(String(8))
    # Exact source spelling (provenance). The canonical, displayed identity is manufacturer_ref / vehicle_model.
    manufacturer: Mapped[str | None] = mapped_column(String(120))
    model: Mapped[str | None] = mapped_column(String(120))
    manufacturer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("manufacturers.id", ondelete="SET NULL"))
    vehicle_model_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vehicle_models.id", ondelete="SET NULL"))
    class_name: Mapped[str | None] = mapped_column(String(60))
    image_url: Mapped[str | None] = mapped_column(String(500))
    fallback_logo_url: Mapped[str | None] = mapped_column(String(500))  # manufacturer logo / silhouette
    competition: Mapped[str | None] = mapped_column(String(60))  # e.g. "Sprint Cup" / "Endurance Cup"
    source_name: Mapped[str | None] = mapped_column(String(200))  # NULL = hand-entered / development seed
    source_url: Mapped[str | None] = mapped_column(String(500))
    checked_at: Mapped[datetime | None] = utc_col(nullable=True)
    team: Mapped[Team] = relationship()
    season: Mapped[Season] = relationship()
    manufacturer_ref: Mapped[Manufacturer | None] = relationship()
    vehicle_model: Mapped[VehicleModel | None] = relationship()
    drivers: Mapped[list[VehicleEntryDriver]] = relationship(
        back_populates="entry", cascade="all, delete-orphan", order_by="VehicleEntryDriver.position"
    )


class Driver(Base):
    __tablename__ = "drivers"
    id: Mapped[uuid.UUID] = uuid_pk()
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    nationality_code: Mapped[str | None] = mapped_column(String(2))
    birth_date: Mapped[date | None] = mapped_column(Date)
    image_url: Mapped[str | None] = mapped_column(String(500))  # portrait; not populated in this milestone
    aliases: Mapped[list[DriverAlias]] = relationship(back_populates="driver", cascade="all, delete-orphan")

    @property
    def canonical_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class VehicleEntryDriver(Base):
    __tablename__ = "vehicle_entry_drivers"
    __table_args__ = (
        UniqueConstraint("vehicle_entry_id", "driver_id"),
        Index("ix_vehicle_entry_drivers_driver_id", "driver_id"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    vehicle_entry_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicle_entries.id", ondelete="CASCADE"))
    driver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("drivers.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # display order
    role: Mapped[str | None] = mapped_column(String(40))  # e.g. "driver", "reserve", "substitute"
    entry: Mapped[VehicleEntry] = relationship(back_populates="drivers")
    driver: Mapped[Driver] = relationship()
