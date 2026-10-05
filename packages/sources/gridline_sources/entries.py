"""Entry-list capabilities.

An adapter is a MotorsportSource (schedule) and MAY additionally implement:

  EntryListSource          who is entered in which car at which event      (GTWC, WEC)
  SessionAssignmentSource  which driver took part in which session         (no current source exposes this)

Capabilities are structural protocols, so a championship only implements what its official source
actually publishes. Like the schedule layer, nothing here touches the database.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol, runtime_checkable

from gridline_shared import slugify

from .base import SourceIssue


@dataclass(frozen=True)
class RawEntries:
    """Raw payloads of one entry-list fetch, keyed by name (URL-derived for live, filename for fixtures)."""

    source_url: str
    fetched_at: datetime
    documents: dict[str, str]
    is_fixture: bool = False
    # event key -> reason the event could not be fetched. The event is quarantined by the parser.
    fetch_errors: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EntryFetchPlan:
    """What the sync engine already trusts, so a source can avoid re-fetching it every cycle."""

    settled_events: frozenset[str] = frozenset()  # event_external_ids: finished long ago and already stored


@dataclass(frozen=True)
class ParsedDriver:
    first_name: str
    last_name: str
    nationality_code: str | None = None  # ISO 3166-1 alpha-2, only when the source states it
    external_id: str | None = None  # the source's own driver identifier, when it has one (F1: 'CHALEC01')
    birth_date: date | None = None  # only when the source states it

    @property
    def slug(self) -> str:
        return slugify(f"{self.first_name} {self.last_name}")


@dataclass(frozen=True)
class ParsedEntry:
    """One car at one event (or, with `event_external_id=None`, in the season-wide roster).

    `drivers` is in the order the source publishes them. `manufacturer` / `model` are the source's exact spellings;
    the importer maps them onto canonical Manufacturer / VehicleModel rows."""

    season_year: int
    event_external_id: str | None  # same key the schedule adapter uses for the Event; None = season-wide roster
    race_number: str | None  # None only where the source does not state it (never guessed)
    team_name: str
    drivers: tuple[ParsedDriver, ...]
    source_url: str
    team_external_id: str | None = None  # the source's own team key (F1: 'ferrari')
    team_aliases: tuple[str, ...] = ()  # other spellings the same source gives the team (F1: the full legal name)
    manufacturer: str | None = None
    model: str | None = None
    class_name: str | None = None
    competition: str | None = None  # e.g. "Sprint Cup" / "Endurance Cup"


@dataclass
class EntryParseResult:
    entries: list[ParsedEntry]
    issues: list[SourceIssue] = field(default_factory=list)
    # Events whose entry list was read successfully (even if some rows were dropped). Anything not in here
    # is left exactly as stored.
    events_parsed: set[str] = field(default_factory=set)


@runtime_checkable
class EntryListSource(Protocol):
    source_id: str
    entries_url: str
    entries_limitation: str | None

    async def fetch_entries(self, plan: EntryFetchPlan) -> RawEntries: ...

    def parse_entries(self, raw: RawEntries) -> EntryParseResult: ...

    def load_entries_fixture(self) -> RawEntries: ...


@dataclass(frozen=True)
class ParsedSessionAssignment:
    """A driver who took part in one session of one car's weekend (only when the source says so explicitly)."""

    season_year: int
    event_external_id: str
    session_external_id: str
    race_number: str
    driver: ParsedDriver
    source_url: str


@runtime_checkable
class SessionAssignmentSource(Protocol):
    source_id: str

    async def fetch_assignments(self) -> RawEntries: ...

    def parse_assignments(self, raw: RawEntries) -> list[ParsedSessionAssignment]: ...


def supports_entries(source: object) -> bool:
    return isinstance(source, EntryListSource)


_SMALL = {"of", "de", "by", "the", "and", "du", "la", "le", "van", "von", "der", "den", "di", "da", "del"}
_BRAND_CASING = {"totalenergies": "TotalEnergies", "mclaren": "McLaren", "bmw": "BMW", "amg": "AMG", "tf": "TF"}


PLACEHOLDERS = {"tba", "tbc", "tbd", "/", "-", "\u2013", "\u2014", "?", "n/a"}


def is_placeholder(text: str) -> bool:
    """'TBA' / '/' in a driver slot: the source has not announced that driver yet."""
    return clean(text).lower() in PLACEHOLDERS or not clean(text)


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def _cap(word: str) -> str:
    return re.sub(r"[^\W\d_]+", lambda m: m.group().capitalize(), word)


def smart_title(text: str) -> str:
    """Turn an ALL-CAPS organisation name into display case. Mixed-case input is returned untouched.

    Short tokens stay upper-case (BMW, WRT, AF), joining words go lower-case, known brand spellings win."""
    text = clean(text)
    if text != text.upper() or not any(c.isalpha() for c in text):
        return text
    out = []
    for i, tok in enumerate(text.split(" ")):
        low = tok.lower()
        if low in _BRAND_CASING:
            out.append(_BRAND_CASING[low])
        elif i > 0 and low in _SMALL:
            out.append(low)
        elif len(tok) <= 3 and tok.isalpha() and low not in _SMALL | {"the"}:
            out.append(tok)
        else:
            out.append(_cap(tok))
    return " ".join(out)


_SURNAME_PARTICLES = {"van", "von", "der", "den", "de", "di", "da", "del", "della", "du", "dos", "das", "ten", "ter", "le", "la"}


def surname_case(text: str) -> str:
    words = [w.lower() for w in clean(text).split(" ")]
    return " ".join(w if (i > 0 and w in _SURNAME_PARTICLES) else _cap(w) for i, w in enumerate(words))


def split_caps_surname(full: str) -> tuple[str, str] | None:
    """'Kelvin VAN DER LINDE' -> ('Kelvin', 'Van der Linde'). The source marks the surname in capitals;
    without that marker there is no safe split, so None."""
    tokens = clean(full).split(" ")
    idx = next((i for i, t in enumerate(tokens) if len(t) > 1 and t == t.upper() and any(c.isalpha() for c in t)), None)
    if idx is None or idx == 0:
        return None
    if not all(t == t.upper() for t in tokens[idx:]):
        return None
    return " ".join(tokens[:idx]), surname_case(" ".join(tokens[idx:]))


# Manufacturers named in SRO car strings ("Mercedes-AMG GT3 EVO"). Longest first.
_GT_MAKES = ["Aston Martin", "Mercedes-AMG", "Lamborghini", "Corvette", "McLaren", "Porsche", "Ferrari",
             "Lexus", "Audi", "BMW", "Ford"]


def split_make_model(car: str, makes: list[str] = _GT_MAKES) -> tuple[str | None, str]:
    car = clean(car)
    for make in sorted(makes, key=len, reverse=True):
        if car.lower().startswith(make.lower() + " "):
            return make, car[len(make):].strip()
    return None, car
