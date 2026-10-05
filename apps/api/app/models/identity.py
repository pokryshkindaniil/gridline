"""Canonical entities and their source aliases.

  Manufacturer ─┬─ ManufacturerAlias        (Ferrari)
                └─ VehicleModel             (499P, SF-26, 296 GT3 EVO)  ← VehicleEntry.vehicle_model_id
  Team ──── TeamAlias                       (team identity is per series: `teams.series_id`)
  Driver ── DriverAlias

An alias row is the exact spelling a source used (`source_value`) plus the comparison key (`normalized_value`) and,
when the source has one, its own identifier. (source_name, normalized_value) is unique: the same spelling from two
different sources may legitimately mean two different entities, so matching is always source-aware.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, utc_col, utcnow, uuid_pk


class Manufacturer(Base):
    __tablename__ = "manufacturers"
    id: Mapped[uuid.UUID] = uuid_pk()
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    canonical_name: Mapped[str] = mapped_column(String(120))
    logo_url: Mapped[str | None] = mapped_column(String(500))
    aliases: Mapped[list[ManufacturerAlias]] = relationship(back_populates="manufacturer", cascade="all, delete-orphan")
    models: Mapped[list[VehicleModel]] = relationship(back_populates="manufacturer")


class VehicleModel(Base):
    """A car model by a manufacturer: 'SF-26', '499P', 'M4 GT3 EVO'. Not the team's car #16, which is a VehicleEntry."""

    __tablename__ = "vehicle_models"
    __table_args__ = (UniqueConstraint("manufacturer_id", "slug"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    manufacturer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("manufacturers.id", ondelete="CASCADE"))
    slug: Mapped[str] = mapped_column(String(120))
    canonical_name: Mapped[str] = mapped_column(String(120))
    season_year: Mapped[int | None] = mapped_column(Integer)  # a model built for one season (F1 chassis), else NULL
    category: Mapped[str | None] = mapped_column(String(60))  # 'Formula 1', 'Hypercar', 'LMGT3', 'GT3'
    source_name: Mapped[str | None] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(String(500))
    checked_at: Mapped[datetime | None] = utc_col(nullable=True)
    manufacturer: Mapped[Manufacturer] = relationship(back_populates="models")


class _AliasMixin:
    source_name: Mapped[str] = mapped_column(String(60))  # adapter id: 'formula1', 'fia_wec', 'gt_world_challenge', …
    source_value: Mapped[str] = mapped_column(String(300))  # exact spelling as published
    normalized_value: Mapped[str] = mapped_column(String(300))
    first_seen_at: Mapped[datetime] = utc_col(default=utcnow)


class DriverAlias(_AliasMixin, Base):
    __tablename__ = "driver_aliases"
    __table_args__ = (
        UniqueConstraint("source_name", "normalized_value", name="uq_driver_aliases_source_value"),
        Index("ix_driver_aliases_driver_id", "driver_id"),
        Index("ix_driver_aliases_source_external_id", "source_name", "source_external_id"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    driver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("drivers.id", ondelete="CASCADE"))
    source_external_id: Mapped[str | None] = mapped_column(String(120))
    driver: Mapped[Driver] = relationship(back_populates="aliases")  # noqa: F821


class TeamAlias(_AliasMixin, Base):
    __tablename__ = "team_aliases"
    __table_args__ = (
        UniqueConstraint("source_name", "normalized_value", name="uq_team_aliases_source_value"),
        Index("ix_team_aliases_team_id", "team_id"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    source_external_id: Mapped[str | None] = mapped_column(String(120))
    team: Mapped[Team] = relationship(back_populates="aliases")  # noqa: F821


class ManufacturerAlias(_AliasMixin, Base):
    __tablename__ = "manufacturer_aliases"
    __table_args__ = (UniqueConstraint("source_name", "normalized_value", name="uq_manufacturer_aliases_source_value"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    manufacturer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("manufacturers.id", ondelete="CASCADE"))
    manufacturer: Mapped[Manufacturer] = relationship(back_populates="aliases")
