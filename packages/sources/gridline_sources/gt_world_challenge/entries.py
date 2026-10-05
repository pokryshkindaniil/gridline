"""Parse SRO GT World Challenge Europe entry lists.

Official pages:
  /entry-lists                         season index: one row per event, 'View List' link when published
  /entry-list/{year}/{event-slug}      one table: Car # | Team | Driver 1..N | Car | Class
  /calendar                            maps the event slug to the numeric event id the schedule adapter uses

The page lists drivers in the published order (Driver 1, Driver 2, ...). Sprint Cup lists carry 2 drivers,
Endurance Cup lists 3 (4 at the 24 Hours of Spa). The same car number can carry a different crew at every event,
so entries are always event-scoped. Nothing is inferred: a row we cannot read fully quarantines its event.
"""

from __future__ import annotations

import html
import re
import urllib.parse

from bs4 import BeautifulSoup

from ..base import SourceError, SourceIssue
from ..entries import (
    EntryParseResult,
    ParsedDriver,
    ParsedEntry,
    RawEntries,
    clean,
    is_placeholder,
    split_caps_surname,
    split_make_model,
)

SITE = "https://www.gt-world-challenge-europe.com"

# Flag CSS class (IOC-style) -> ISO 3166-1 alpha-2. Unlisted classes give no nationality (never guessed).
FLAG = {
    "gbr": "GB", "ger": "DE", "fra": "FR", "ita": "IT", "bel": "BE", "den": "DK", "sui": "CH", "ned": "NL",
    "usa": "US", "aut": "AT", "esp": "ES", "rsa": "ZA", "bra": "BR", "mon": "MC", "swe": "SE", "uae": "AE",
    "arg": "AR", "tha": "TH", "por": "PT", "aus": "AU", "slo": "SI", "per": "PE", "isr": "IL", "can": "CA",
    "lux": "LU", "irl": "IE", "hkg": "HK", "fin": "FI", "and": "AD", "rus": "RU", "mex": "MX", "ind": "IN",
    "smr": "SM", "oma": "OM", "idn": "ID", "ecu": "EC", "ukr": "UA", "nor": "NO", "mas": "MY", "grc": "GR",
    "gre": "GR", "chn": "CN", "zwe": "ZW", "tur": "TR", "pol": "PL", "phi": "PH", "jpn": "JP", "hun": "HU",
    "est": "EE", "ago": "AO",
}
CLASS_LABEL = {"PRO": "Pro", "SILVER": "Silver", "GOLD": "Gold", "BRONZE": "Bronze", "PRO-AM": "Pro-Am"}
COMPETITION = re.compile(r"\b(Sprint|Endurance) Cup\b")
YEAR = re.compile(r"Entry List (\d{4})")


def _norm_slug(slug: str) -> str:
    return urllib.parse.unquote(html.unescape(slug)).lower()


def doc_key(slug: str) -> str:
    return "entry_" + urllib.parse.quote(slug, safe="") + ".html"  # ASCII-safe even for 'nürburgring'


def index_links(index_html: str) -> dict[str, str]:
    """entry-list slug -> path, for events whose list is published ('Not available' rows have no link)."""
    out = {}
    for href in re.findall(r'href="(/entry-list/\d{4}/[^"]+)"', index_html):
        out[_norm_slug(href.rsplit("/", 1)[-1])] = html.unescape(href)
    return out


def calendar_event_ids(calendar_html: str) -> dict[str, str]:
    """event slug -> schedule event_external_id ('e254'), from the /event/{id}/{slug} links."""
    out = {}
    for eid, slug in re.findall(r'href="/event/(\d+)/([^"]+)"', calendar_html):
        out[_norm_slug(slug)] = f"e{eid}"
    return out


def parse_entry_page(doc: str, event_id: str, url: str) -> tuple[int, list[ParsedEntry]]:
    soup = BeautifulSoup(doc, "lxml")
    title = clean(soup.title.get_text()) if soup.title else ""
    m = YEAR.search(title)
    if not m:
        raise SourceError(f"{event_id}: no 'Entry List <year>' in page title; markup changed?")
    year = int(m[1])
    heading = " ".join(h.get_text(" ", strip=True) for h in soup.select("main h1, main h2, main h3"))
    cup = COMPETITION.search(heading)
    competition = f"{cup[1]} Cup" if cup else None

    table = soup.select_one("main table")
    if table is None:
        raise SourceError(f"{event_id}: no entry table; markup changed?")
    header = [clean(th.get_text()) for th in table.select("thead th")]
    driver_cols = [i for i, h in enumerate(header) if re.fullmatch(r"Driver \d", h)]
    try:
        c_num, c_team, c_car, c_class = (header.index(n) for n in ("Car #", "Team", "Car", "Class"))
    except ValueError as exc:
        raise SourceError(f"{event_id}: unexpected entry table columns {header}") from exc
    if not driver_cols:
        raise SourceError(f"{event_id}: entry table has no driver columns {header}")

    entries: list[ParsedEntry] = []
    seen: set[str] = set()
    rows = table.select("tbody tr")
    if not rows:
        raise SourceError(f"{event_id}: entry table is empty")
    for tr in rows:
        cells = tr.find_all("td")
        if len(cells) != len(header):
            raise SourceError(f"{event_id}: row has {len(cells)} cells, expected {len(header)}")
        number = clean(cells[c_num].get_text())
        team = clean(cells[c_team].get_text())
        if not number or not team:
            raise SourceError(f"{event_id}: row without car number or team")
        if number in seen:
            raise SourceError(f"{event_id}: car #{number} listed twice")
        seen.add(number)

        drivers: list[ParsedDriver] = []
        for i in driver_cols:
            cell = cells[i]
            name = clean(cell.get_text())
            if is_placeholder(name):
                continue  # unannounced slot (empty, 'TBA', '/'): the car is entered, that driver is not known yet
            split = split_caps_surname(name)
            if split is None:
                raise SourceError(f"{event_id} #{number}: cannot split driver name {name!r} (surname not in capitals)")
            flag = cell.select_one(".table__flag")
            code = next((FLAG[c] for c in (flag.get("class") or []) if c in FLAG), None) if flag else None
            drivers.append(ParsedDriver(split[0], split[1], code))
        if len({d.slug for d in drivers}) != len(drivers):
            raise SourceError(f"{event_id} #{number}: driver listed twice")

        make, model = split_make_model(clean(cells[c_car].get_text()))
        cls = clean(cells[c_class].get_text()).upper()
        entries.append(ParsedEntry(
            season_year=year, event_external_id=event_id, race_number=number, team_name=team,
            drivers=tuple(drivers), source_url=url, manufacturer=make, model=model or None,
            class_name=CLASS_LABEL.get(cls, cls.title() or None), competition=competition,
        ))
    return year, entries


def parse_entry_documents(raw: RawEntries) -> EntryParseResult:
    index = raw.documents.get("entry-lists.html")
    calendar = raw.documents.get("calendar.html")
    if index is None or calendar is None:
        raise SourceError("GTWC entries: index or calendar document missing")
    links = index_links(index)
    ids = calendar_event_ids(calendar)
    if not ids:
        raise SourceError("GTWC entries: calendar lists no /event/ links; markup changed?")
    if not links:
        if "no-link" not in index and "entry-lists__link-button" not in index:
            raise SourceError("GTWC entries: entry-list index has no event rows; markup changed?")
        return EntryParseResult([])  # nothing published yet (every row says 'Not available')

    result = EntryParseResult([])
    for slug, path in sorted(links.items()):
        label = slug
        event_id = ids.get(slug)
        if event_id is None:
            result.issues.append(SourceIssue(label, f"no scheduled event for entry-list slug {slug!r}"))
            continue
        if label in raw.fetch_errors:
            result.issues.append(SourceIssue(label, raw.fetch_errors[label]))
            continue
        doc = raw.documents.get(doc_key(slug))
        if doc is None:
            continue  # settled: deliberately not fetched this cycle, stored data stays as is
        try:
            _year, entries = parse_entry_page(doc, event_id, SITE + path)
        except (SourceError, ValueError, KeyError, AttributeError) as exc:
            result.issues.append(SourceIssue(label, f"{type(exc).__name__}: {exc}"))
            continue
        result.entries.extend(entries)
        result.events_parsed.add(event_id)
    return result
