"""Parse the official Formula 1 season roster."""

from __future__ import annotations

import re
from datetime import date, datetime

from bs4 import BeautifulSoup
from gridline_shared import slugify

from ..base import SourceError, SourceIssue
from ..entries import EntryParseResult, ParsedDriver, ParsedEntry, RawEntries, clean

SITE = "https://www.formula1.com"

# Codes used by formula1.com result tables (FIA/IOC style) → ISO 3166-1 alpha-2. A code missing here is reported
# as an issue and the nationality is left empty rather than guessed.
NATIONALITY = {
    "GBR": "GB", "MON": "MC", "NED": "NL", "AUS": "AU", "FRA": "FR", "GER": "DE", "ITA": "IT", "ESP": "ES",
    "THA": "TH", "ARG": "AR", "BRA": "BR", "CAN": "CA", "FIN": "FI", "MEX": "MX", "NZL": "NZ", "JPN": "JP",
    "CHN": "CN", "USA": "US", "DEN": "DK", "AUT": "AT", "BEL": "BE", "SUI": "CH", "POL": "PL", "RUS": "RU",
    "IRL": "IE", "SWE": "SE", "POR": "PT", "IND": "IN", "INA": "ID", "VEN": "VE", "COL": "CO", "CHI": "CL",
    "HUN": "HU", "ISR": "IL", "UAE": "AE", "KSA": "SA", "EST": "EE", "CZE": "CZ", "SGP": "SG", "MAS": "MY",
}

# Race-result pages are fetched newest first until every roster driver has a number, never more than this.
MAX_RESULT_PAGES = 6


def team_key(slug: str) -> str:
    return f"team_{slug}.html"


def driver_key(slug: str) -> str:
    return f"driver_{slug}.html"


def result_key(race_id: str) -> str:
    return f"result_{race_id}.html"


TEAMS_KEY, STANDINGS_KEY, RACES_KEY = "teams.html", "standings.html", "races.html"


def parse_team_index(doc: str) -> list[tuple[str, str]]:
    """[(team slug, display name)] in page order."""
    soup = BeautifulSoup(doc, "lxml")
    out: dict[str, str] = {}
    for a in soup.select('a[href^="/en/teams/"]'):
        slug = a["href"].rstrip("/").rsplit("/", 1)[-1]
        strings = list(a.stripped_strings)
        if slug and strings and slug not in out:
            out[slug] = clean(strings[0])
    if not out:
        raise SourceError("F1 /en/teams lists no teams; markup changed?")
    return list(out.items())


def parse_team_page(doc: str) -> dict:
    soup = BeautifulSoup(doc, "lxml")
    data = {clean(dt.get_text()): clean(dd.get_text()) for dt in soup.select("dl dt") if (dd := dt.find_next("dd"))}
    drivers: list[str] = []
    for a in soup.select('a[href^="/en/drivers/"]'):
        slug = a["href"].rstrip("/").rsplit("/", 1)[-1]
        if slug not in drivers:
            drivers.append(slug)
    h1 = soup.select_one("h1")
    return {"full_name": data.get("Full Team Name"), "chassis": data.get("Chassis"),
            "power_unit": data.get("Power Unit"), "drivers": drivers, "heading": clean(h1.get_text()) if h1 else None}


def _driver_cell(cell) -> tuple[str, str] | None:
    # leaf <span>s with text, in order: first name, surname, then the 3-letter code (shown on narrow screens)
    spans = [clean(s.get_text()) for s in cell.find_all("span") if not s.find(True) and clean(s.get_text())]
    return (spans[0], spans[1]) if len(spans) >= 2 and spans[0] and spans[1] else None


def parse_standings(doc: str) -> dict[tuple[str, str], dict]:
    """(first, last) → {id, slug, nationality (3-letter), team}"""
    soup = BeautifulSoup(doc, "lxml")
    table = soup.select_one("table")
    if table is None:
        raise SourceError("F1 driver standings: no table; markup changed?")
    header = [clean(th.get_text()) for th in table.select("thead th")]
    if header[:2] != ["Pos.", "Driver"] or "Nationality" not in header or "Team" not in header:
        raise SourceError(f"F1 driver standings: unexpected columns {header}")
    c_nat, c_team = header.index("Nationality"), header.index("Team")
    out = {}
    for tr in table.select("tbody tr"):
        cells = tr.find_all("td")
        if len(cells) <= max(c_nat, c_team, 1):
            continue
        a = cells[1].select_one("a[href]")
        name = _driver_cell(cells[1])
        m = re.search(r"/drivers/([A-Z0-9]+)/([a-z0-9-]+)", a["href"] if a else "")
        if not (name and m):
            continue
        out[name] = {"id": m[1], "slug": m[2], "nationality": clean(cells[c_nat].get_text()),
                     "team": clean(cells[c_team].get_text())}
    if not out:
        raise SourceError("F1 driver standings: no driver rows")
    return out


def parse_race_index(doc: str) -> list[tuple[str, str]]:
    """(race id, page path) with a published result, newest first (the page lists the season in calendar order)."""
    soup = BeautifulSoup(doc, "lxml")
    found: dict[str, str] = {}
    for a in soup.select('table a[href*="/race-result"]'):  # the results table only: menus also link future races
        m = re.search(r"/results/\d{4}/races/(\d+)/", a["href"])
        if m:
            found.setdefault(m[1], a["href"])
    return list(reversed(found.items()))


def parse_race_numbers(doc: str) -> dict[tuple[str, str], str]:
    soup = BeautifulSoup(doc, "lxml")
    table = soup.select_one("table")
    if table is None:
        raise SourceError("F1 race result: no table")
    header = [clean(th.get_text()) for th in table.select("thead th")]
    if "No." not in header or "Driver" not in header:
        raise SourceError(f"F1 race result: unexpected columns {header}")
    c_no, c_drv = header.index("No."), header.index("Driver")
    out = {}
    for tr in table.select("tbody tr"):
        cells = tr.find_all("td")
        if len(cells) <= max(c_no, c_drv):
            continue
        name, number = _driver_cell(cells[c_drv]), clean(cells[c_no].get_text())
        if name and number.isdigit():
            out[name] = number
    return out


def parse_birth_date(doc: str) -> date | None:
    soup = BeautifulSoup(doc, "lxml")
    for dt in soup.select("dt"):
        if clean(dt.get_text()) == "Date of Birth" and (dd := dt.find_next("dd")):
            try:
                return datetime.strptime(clean(dd.get_text()), "%d/%m/%Y").date()
            except ValueError:
                return None
    return None


def split_display_name(slug: str, standings: dict[tuple[str, str], dict]) -> tuple[str, str] | None:
    for name, row in standings.items():
        if row["slug"] == slug:
            return name
    return None


def constructor_name(display: str) -> str:
    return re.sub(r"\s+F1 Team$", "", display).strip()


def parse_roster(raw: RawEntries, year: int) -> EntryParseResult:
    docs = raw.documents
    for key in (TEAMS_KEY, STANDINGS_KEY):
        if key not in docs:
            raise SourceError(f"F1 roster: {key} missing")
    teams = parse_team_index(docs[TEAMS_KEY])
    standings = parse_standings(docs[STANDINGS_KEY])
    by_slug = {row["slug"]: (name, row) for name, row in standings.items()}

    numbers: dict[tuple[str, str], str] = {}
    for key in sorted((k for k in docs if k.startswith("result_")), key=lambda k: int(k[7:-5]), reverse=True):
        for name, no in parse_race_numbers(docs[key]).items():
            numbers.setdefault(name, no)  # newest race wins

    result = EntryParseResult([])
    for team_slug, display in teams:
        url = f"{SITE}/en/teams/{team_slug}"
        try:
            doc = docs.get(team_key(team_slug))
            if doc is None or "FETCH-ERROR" in doc[:200]:
                raise SourceError((doc or "page not fetched").strip("<!-> \n"))
            page = parse_team_page(doc)
            if not page["chassis"]:
                raise SourceError("team page has no Chassis")
            if not page["drivers"]:
                raise SourceError("team page lists no drivers")
            entries = []
            for dslug in page["drivers"]:
                found = by_slug.get(dslug)
                if found is None:
                    raise SourceError(f"driver {dslug!r} is not in the {year} standings; cannot read name/id")
                (first, last), row = (found[0], found[1])
                code = NATIONALITY.get(row["nationality"])
                if code is None:
                    result.issues.append(SourceIssue(team_slug, f"{first} {last}: nationality {row['nationality']!r} not mapped"))
                birth = parse_birth_date(docs.get(driver_key(dslug), ""))
                drv = ParsedDriver(first, last, code, external_id=row["id"], birth_date=birth)
                entries.append((numbers.get((first, last)), drv))
        except (SourceError, KeyError, ValueError) as exc:
            result.issues.append(SourceIssue(team_slug, f"{type(exc).__name__}: {exc}"))
            continue
        for number, drv in entries:
            result.entries.append(ParsedEntry(
                season_year=year, event_external_id=None, race_number=number, team_name=display,
                drivers=(drv,), source_url=url, team_external_id=team_slug,
                team_aliases=(page["full_name"],) if page["full_name"] and page["full_name"] != display else (),
                manufacturer=constructor_name(display), model=page["chassis"], class_name=None, competition=None,
            ))
            if number is None:
                result.issues.append(SourceIssue(team_slug, f"{drv.first_name} {drv.last_name}: no race number published yet"))
    if not result.entries:
        raise SourceError("F1 roster: no team could be read")
    result.events_parsed = set()  # season-wide: there are no events
    return result


def trim_document(key: str, html: str) -> str:
    """Reduce a captured page to the elements this parser reads (fixtures stay small and reviewable)."""
    soup = BeautifulSoup(html, "lxml")
    out = BeautifulSoup("<!doctype html><html><head><meta charset='utf-8'></head><body></body></html>", "lxml")
    body = out.body

    def keep(el) -> None:
        body.append(BeautifulSoup(str(el), "lxml").body.contents[0])

    if key == TEAMS_KEY or key == RACES_KEY:
        if key == RACES_KEY:
            table = soup.select_one("table")
            for tag in table.find_all(["img", "svg", "picture"]):
                tag.decompose()
            keep(table)
        else:
            for a in soup.select('a[href^="/en/teams/"]'):
                for tag in a.find_all(["img", "svg", "picture"]):
                    tag.decompose()
                keep(a)
    elif key.startswith("team_"):
        h1 = soup.select_one("h1")
        if h1:
            keep(h1)
        dl = soup.select_one("dl")
        for dl in soup.select("dl"):
            if any(clean(dt.get_text()) == "Chassis" for dt in dl.select("dt")):
                keep(dl)
                break
        seen = set()
        for a in soup.select('a[href^="/en/drivers/"]'):
            if a["href"] not in seen:
                seen.add(a["href"])
                body.append(BeautifulSoup(f'<a href="{a["href"]}">{slugify(a["href"])}</a>', "lxml").body.contents[0])
    elif key == STANDINGS_KEY or key.startswith("result_"):
        table = soup.select_one("table")
        for tag in table.find_all(["img", "svg", "picture"]):
            tag.decompose()
        keep(table)
    elif key.startswith("driver_"):
        for dl in soup.select("dl"):
            if any(clean(dt.get_text()) == "Date of Birth" for dt in dl.select("dt")):
                keep(dl)
                break
    return str(out)
