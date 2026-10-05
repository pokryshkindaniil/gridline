"""Enumerations shared by the API, source adapters and calendar renderer."""

from enum import StrEnum


class SeriesCategory(StrEnum):
    FORMULA = "formula"
    ENDURANCE = "endurance"
    GT = "gt"
    RALLY = "rally"
    STOCK_CAR = "stock_car"
    MOTO = "moto"
    OTHER = "other"


class SessionType(StrEnum):
    PRACTICE = "practice"
    QUALIFYING = "qualifying"
    SPRINT = "sprint"
    RACE = "race"
    WARMUP = "warmup"
    TEST = "test"
    OTHER = "other"


class SessionStatus(StrEnum):
    SCHEDULED = "scheduled"
    DELAYED = "delayed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class EventStatus(StrEnum):
    SCHEDULED = "scheduled"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
