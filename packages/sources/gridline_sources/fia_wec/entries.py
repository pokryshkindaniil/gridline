"""Parse official FIA WEC entries (fiawec.com).

The site publishes entries in three layers, all server-rendered HTML:

  /en/page/grid                       'Grid' page: season/race selector. Choosing a race calls the page's own
                                      live-component endpoint, which returns that race's car cards.
  /en/car/{year}/{number}?race={id}   technical sheet of one car AT ONE RACE: team, class, car, drivers in the
                                      published order. Crews differ per race (substitutes, 4th drivers ...).
  /en/driver/{year}/{id}              driver profile: 'First Last' in the title, nationality flag.

Car pages print drivers as 'Surname Firstname' while profiles print 'Firstname Surname'. Combining both is the
only way to split multi-word names without guessing; if they do not agree, the event is quarantined.

Race selector options only exist for races whose grid has been published, so unpublished races are simply absent.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup
from gridline_shared import slugify

from ..base import SourceError, SourceIssue
from ..entries import (
    EntryParseResult,
    ParsedDriver,
    ParsedEntry,
    RawEntries,
    clean,
    smart_title,
    split_make_model,
)

SITE = "https://www.fiawec.com"
GRID_PATH = "/en/page/grid"
WEC_MAKES = ["Aston Martin", "Mercedes", "Alpine", "BMW", "Cadillac", "Corvette", "Ferrari", "Ford", "Genesis",
             "Lexus", "McLaren", "Peugeot", "Porsche", "Toyota", "Lamborghini"]
CLASS_LABEL = {"HYPERCAR": "Hypercar", "LMGT3": "LMGT3"}


# ----------------------------------------------------------------------------- document keys

def car_key(year: int, number: str, race_id: str) -> str:
    return f"car_{year}_{number}_race{race_id}.html"


def grid_key(race_id: str) -> str:
    return f"grid_race{race_id}.html"


def driver_key(year: int, driver_id: str) -> str:
    return f"driver_{year}_{driver_id}.html"


# ----------------------------------------------------------------------------- grid page

@dataclass(frozen=True)
class GridPage:
    year: int
    component_url: str  # '/en/_components/...'
    props: dict
    races: list[tuple[str, str]]  # (race id, race name) for races with a published grid

    def event_external_id(self, race_name: str) -> str:
        return f"{slugify(race_name)}-{self.year}"  # same slug the schedule adapter uses for the race page


def parse_grid_page(doc: str) -> GridPage:
    soup = BeautifulSoup(doc, "lxml")
    comp = soup.select_one('[data-live-name-value*="CompetitorCarList"]')
    if comp is None:
        raise SourceError("WEC grid page: competitor list component not found; markup changed?")
    try:
        props = json.loads(html.unescape(comp["data-live-props-value"]))
        url = comp["data-live-url-value"]
    except (KeyError, json.JSONDecodeError) as exc:
        raise SourceError(f"WEC grid page: unreadable live component props: {exc}") from exc
    year_opt = soup.select_one("#filter-year option[selected]")
    m = re.search(r"\d{4}", year_opt.get_text()) if year_opt else None
    if not m:
        raise SourceError("WEC grid page: selected season not found")
    select = comp.select_one('select[data-model="raceId"]')
    if select is None:
        raise SourceError("WEC grid page: race selector not found; markup changed?")
    races = []
    for opt in select.select("option"):
        value = opt.get("value", "")
        if value.isdigit():
            races.append((value, clean(opt.get_text())))
    if not races and len(select.select("option")) > 1:
        raise SourceError("WEC grid page: race selector has options but none could be read; markup changed?")
    return GridPage(int(m[0]), url, props, races)


def parse_grid_fragment(doc: str) -> list[str]:
    """Car numbers in the grid returned for one race (the 'Grid' cards, in page order)."""
    soup = BeautifulSoup(doc, "lxml")
    nums = []
    for a in soup.select('a[href*="/car/"]'):
        m = re.search(r"/car/\d{4}/([^/?#]+)", a["href"])
        if m and m[1] not in nums:
            nums.append(m[1])
    return nums


# ----------------------------------------------------------------------------- car / driver pages

@dataclass(frozen=True)
class CarPage:
    team: str
    category: str
    car: str
    drivers: list[tuple[str, str]]  # (driver id, 'Surname Firstname' as printed)


def parse_car_page(doc: str) -> CarPage:
    soup = BeautifulSoup(doc, "lxml")
    info = {}
    for label in soup.select("div.fs-11.text-secondary"):
        value = label.find_next_sibling("div")
        if value is not None:
            info[clean(label.get_text())] = clean(value.get_text(" "))
    for key in ("Category", "Car", "Full team name"):
        if not info.get(key):
            raise SourceError(f"car page without '{key}'; markup changed?")
    drivers = []
    for a in soup.select("a.card-driver"):
        m = re.search(r"/driver/\d{4}/(\d+)", a["href"])
        if not m:
            raise SourceError(f"driver card without a profile link: {a['href']!r}")
        drivers.append((m[1], clean(a.get_text(" "))))
    return CarPage(info["Full team name"], info["Category"], info["Car"], drivers)


@dataclass(frozen=True)
class DriverPage:
    full_name: str  # 'First Last' (page title)
    nationality_code: str | None
    first_name: str | None = None  # from the profile heading, which marks the first name explicitly
    last_name: str | None = None


def parse_driver_page(doc: str) -> DriverPage:
    soup = BeautifulSoup(doc, "lxml")
    title = clean(soup.title.get_text()) if soup.title else ""
    m = re.match(r"FIA WEC drivers\s*-\s*(.+)$", title)
    if not m:
        raise SourceError(f"driver page title not recognised: {title!r}")
    first = last = None
    h1 = soup.select_one("h1")
    small = h1.find("small") if h1 else None
    if h1 is not None and small is not None:
        first = clean(small.get_text())
        last = clean(h1.get_text(" ").replace(small.get_text(), "", 1))
        if clean(f"{first} {last}").casefold() != clean(m[1]).casefold():
            first = last = None  # heading and title disagree: do not trust either split
    return DriverPage(clean(m[1]), _nationality(soup), first, last)


def _nationality(soup: BeautifulSoup) -> str | None:
    """ISO code from the flag in the profile's 'Nationality' row. (The page also shows race-calendar flags
    earlier in the document, so the row must be anchored by its label.)"""
    label = soup.find(lambda t: t.name == "span" and clean(t.get_text()).lower() == "nationality")
    row = label.parent if label else None
    flag = row.select_one('[class*="flag:"]') if row else None
    fm = re.search(r"flag:([A-Z]{2})\b", " ".join(flag.get("class", []))) if flag else None
    return fm[1] if fm else None


def driver_name(printed: str, prof: DriverPage) -> tuple[str, str]:
    """(first, last) for a driver. The profile heading marks the first name; the car page's 'Last First' must
    agree with it. Without a marked heading, fall back to matching title against the car page text."""
    if prof.first_name and prof.last_name:
        if sorted(printed.casefold().split()) != sorted(f"{prof.first_name} {prof.last_name}".casefold().split()):
            raise SourceError(f"driver {prof.full_name!r} does not match the car page name {printed!r}")
        return prof.first_name, prof.last_name
    return split_name(printed, prof.full_name)


def split_name(printed: str, full: str) -> tuple[str, str]:
    """Car page prints 'Last First', profile prints 'First Last'. Return (first, last) only when the two agree."""
    p, f = printed.casefold().split(), full.split()
    cands = [j for j in range(1, len(f)) if [w.casefold() for w in f[j:] + f[:j]] == p]
    if len(cands) != 1:
        raise SourceError(f"cannot split driver name {full!r} (car page prints {printed!r})")
    j = cands[0]
    return " ".join(f[:j]), " ".join(f[j:])


def person_case(text: str) -> str:
    """Profile names are normally proper-cased; shout-case ('HASSE CLOT') is normalised, the rest kept."""
    return " ".join(w.capitalize() if w == w.upper() and len(w) > 1 else w for w in text.split(" "))


# ----------------------------------------------------------------------------- whole-document parsing

def parse_entry_documents(raw: RawEntries) -> EntryParseResult:
    grid_doc = raw.documents.get("grid_page.html")
    if grid_doc is None:
        raise SourceError("WEC entries: grid page missing")
    grid = parse_grid_page(grid_doc)

    result = EntryParseResult([])
    driver_cache: dict[str, DriverPage] = {}

    def driver(year: int, did: str) -> DriverPage:
        if did not in driver_cache:
            doc = raw.documents.get(driver_key(year, did))
            if doc is None:
                raise SourceError(f"driver profile {did} not fetched")
            driver_cache[did] = parse_driver_page(doc)
        return driver_cache[did]

    for race_id, race_name in grid.races:
        event_id = grid.event_external_id(race_name)
        if event_id in raw.fetch_errors:
            result.issues.append(SourceIssue(event_id, raw.fetch_errors[event_id]))
            continue
        gdoc = raw.documents.get(grid_key(race_id))
        if gdoc is None:
            continue  # settled: not fetched this cycle, stored data stays as is
        try:
            numbers = parse_grid_fragment(gdoc)
            if not numbers:
                raise SourceError("race grid lists no cars")
            entries = []
            seen = set()
            for num in numbers:
                cdoc = raw.documents.get(car_key(grid.year, num, race_id))
                if cdoc is None:
                    raise SourceError(f"car #{num} page not fetched")
                car = parse_car_page(cdoc)
                if num in seen:
                    raise SourceError(f"car #{num} listed twice")
                seen.add(num)
                drivers = []
                for did, printed in car.drivers:
                    prof = driver(grid.year, did)
                    first, last = driver_name(printed, prof)
                    drivers.append(ParsedDriver(person_case(first), person_case(last), prof.nationality_code))
                if len({d.slug for d in drivers}) != len(drivers):
                    raise SourceError(f"car #{num}: driver listed twice")
                mfr_raw, _, model_raw = car.car.partition(" - ")
                if not model_raw:
                    make, model_raw = split_make_model(car.car, WEC_MAKES)
                    mfr_raw = make or ""
                mfr = next((m for m in WEC_MAKES if m.casefold() == mfr_raw.casefold()), smart_title(mfr_raw))
                entries.append(ParsedEntry(
                    season_year=grid.year, event_external_id=event_id, race_number=num,
                    team_name=smart_title(car.team), drivers=tuple(drivers),
                    source_url=f"{SITE}/en/car/{grid.year}/{num}?race={race_id}",
                    manufacturer=mfr or None, model=clean(model_raw) or None,
                    class_name=CLASS_LABEL.get(car.category.upper(), car.category),
                ))
        except SourceError as exc:
            result.issues.append(SourceIssue(event_id, f"{type(exc).__name__}: {exc}"))
            continue
        result.entries.extend(entries)
        result.events_parsed.add(event_id)
    return result
