"""Capture trimmed real fixtures for the live adapters (run manually; polite, sequential).

    python scripts/capture_fixtures.py formula1|fia_wec
    python scripts/capture_fixtures.py gtwc_entries|wec_entries    entry lists (see entry_fixtures/ per adapter)

Entry fixtures keep the official markup verbatim but drop everything the parsers do not read (scripts, header,
footer, tracking). `wec_entries` runs the adapter's own live fetch, then keeps a few races.
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import httpx

UA = "GRIDLINE/0.1 (fixture capture; private development)"
ROOT = Path(__file__).resolve().parent.parent / "gridline_sources"


def get(c: httpx.Client, url: str) -> str:
    time.sleep(0.5)
    r = c.get(url, headers={"User-Agent": UA}, follow_redirects=True, timeout=20)
    r.raise_for_status()
    return r.text


def f1(year: int) -> None:
    out = ROOT / "formula1" / "fixtures"
    for old in out.iterdir():
        old.unlink()
    with httpx.Client() as c:
        index = get(c, f"https://www.formula1.com/en/racing/{year}")
        slugs = sorted(set(re.findall(rf"/en/racing/{year}/([a-z0-9-]+)", index)))
        (out / "index.html").write_text("\n".join(f'<a href="/en/racing/{year}/{s}">{s}</a>' for s in slugs))
        for s in slugs:
            if s.startswith("pre-season-testing"):
                continue
            h = get(c, f"https://www.formula1.com/en/racing/{year}/{s}")
            ld = re.search(r'<script[^>]*type="application/ld\+json"[^>]*>.*?</script>', h, re.S)
            i = h.find("meetingSessions")
            snippet = h[max(0, i - 20): i + 1200] if i >= 0 else ""
            (out / f"race_{s}.html").write_text(
                f"<!-- trimmed capture of /en/racing/{year}/{s} -->\n{ld.group(0) if ld else ''}\n<script>{snippet}</script>\n"
            )
            print("captured", s, bool(ld), i >= 0)


def wec(year: int) -> None:
    out = ROOT / "fia_wec" / "fixtures"
    for old in out.iterdir():
        old.unlink()
    with httpx.Client() as c:
        season = get(c, f"https://www.fiawec.com/en/season/{year}")
        slugs = sorted(set(re.findall(rf'href="/en/race/([a-z0-9-]+-{year})"', season)))
        for s in slugs:
            h = get(c, f"https://www.fiawec.com/en/race/{s}")
            ld = re.search(r'<script[^>]*type="application/ld\+json"[^>]*>(?:(?!</script>).)*"SportsEvent".*?</script>', h, re.S)
            stamps = [f'<span data-timestamp="{t}"></span>' for t in re.findall(r'data-timestamp="(\d+)"', h)]
            cal = re.search(r'href="(/en/race/calendar/\d+)"', h)
            (out / f"race_{s}.html").write_text(
                f"<!-- trimmed capture of /en/race/{s} -->\n{ld.group(0) if ld else ''}\n"
                + "\n".join(stamps) + (f'\n<a href="{cal.group(1)}">Add to my calendar</a>' if cal else "") + "\n"
            )
            if cal:
                (out / f"race_{s}.ics").write_text(get(c, "https://www.fiawec.com" + cal.group(1)))
            print("captured", s, bool(ld), len(stamps), bool(cal))


def _gtwc_trim(doc: str, url: str, with_headings: bool = True) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(doc, "lxml")
    title = soup.title.get_text(strip=True) if soup.title else ""
    heads = "".join(str(h) for h in soup.select("main h1, main h2, main h3")) if with_headings else ""
    table = soup.select_one("main table")
    return (f"<!-- trimmed capture of {url} -->\n<html><head><title>{title}</title></head><body><main>"
            f"{heads}{table}</main></body></html>\n")


def gtwc_entries(year: int) -> None:
    from urllib.parse import quote

    site = "https://www.gt-world-challenge-europe.com"
    out = ROOT / "gt_world_challenge" / "entry_fixtures"
    out.mkdir(exist_ok=True)
    for old in out.iterdir():
        old.unlink()
    with httpx.Client() as c:
        index = get(c, f"{site}/entry-lists")
        (out / "entry-lists.html").write_text(_gtwc_trim(index, f"{site}/entry-lists", with_headings=False))
        for href in sorted(set(re.findall(rf'href="(/entry-list/{year}/[^"]+)"', index))):
            import html as _h
            import urllib.parse as _u

            slug = _u.unquote(_h.unescape(href.rsplit("/", 1)[-1])).lower()
            doc = get(c, site + _h.unescape(href).replace("ü", "%C3%BC"))
            (out / f"entry_{quote(slug, safe='')}.html").write_text(_gtwc_trim(doc, site + href))
            print("captured", slug)


def wec_entries(year: int) -> None:
    """Live-fetch every published race grid with the adapter itself (~7 min, polite), keep prologue/Spa/COTA.

    WEC_RAW_JSON=<file> reuses documents saved from an earlier live fetch instead of fetching again."""
    import asyncio
    import json
    import os

    sys.path.insert(0, str(ROOT.parent))
    from gridline_sources import EntryFetchPlan, get_source
    from gridline_sources.fia_wec.entries import (
        car_key,
        driver_key,
        grid_key,
        parse_car_page,
        parse_grid_fragment,
        parse_grid_page,
    )

    out = ROOT / "fia_wec" / "entry_fixtures"
    out.mkdir(exist_ok=True)
    for old in out.iterdir():
        old.unlink()
    src = get_source("fia_wec")
    if os.environ.get("WEC_RAW_JSON"):
        docs = json.load(open(os.environ["WEC_RAW_JSON"]))
    else:
        docs = asyncio.run(src.fetch_entries(EntryFetchPlan())).documents
    grid = parse_grid_page(docs["grid_page.html"])
    keep_names = {"OFFICIAL PROLOGUE - IMOLA", "TOTALENERGIES 6 HOURS OF SPA-FRANCORCHAMPS", "LONE STAR LE MANS"}
    keep = [(rid, n) for rid, n in grid.races if n in keep_names]
    from html import escape as html_escape

    from bs4 import BeautifulSoup

    def car_trim(doc: str) -> str:
        soup = BeautifulSoup(doc, "lxml")
        labels = "".join(str(x.parent) for x in soup.select("div.fs-11.text-secondary"))
        drivers = "".join(str(a) for a in soup.select("a.card-driver"))
        return f"<html><head><title>{soup.title.get_text(strip=True)}</title></head><body>{labels}{drivers}</body></html>\n"

    def driver_trim(doc: str) -> str:
        soup = BeautifulSoup(doc, "lxml")
        label = soup.find(lambda t: t.name == "span" and t.get_text(strip=True).lower() == "nationality")
        return (f"<html><head><title>{soup.title.get_text(strip=True)}</title></head><body>"
                f"{label.parent.parent if label else ''}</body></html>\n")

    # the grid page: keep the live component wrapper (props) and a race selector limited to the kept races
    gp = BeautifulSoup(docs["grid_page.html"], "lxml")
    comp = gp.select_one('[data-live-name-value*="CompetitorCarList"]')
    sel = comp.select_one('select[data-model="raceId"]')
    for opt in sel.select("option"):
        if opt.get("value", "").isdigit() and opt["value"] not in {rid for rid, _ in keep}:
            opt.decompose()
    attrs = " ".join(f'{k}="{html_escape(v)}"' for k, v in comp.attrs.items() if k.startswith("data-live"))
    (out / "grid_page.html").write_text(
        f"<html><body>{gp.select_one('#filter-year')}<div {attrs}>{sel}</div></body></html>\n")
    done_drivers: set[str] = set()
    for rid, _name in keep:
        (out / grid_key(rid)).write_text(
            "".join(f'<a href="{a["href"]}">{a.get_text(strip=True)}</a>\n'
                    for a in BeautifulSoup(docs[grid_key(rid)], "lxml").select('a[href*="/car/"]')))
        for num in parse_grid_fragment(docs[grid_key(rid)]):
            doc = docs[car_key(year, num, rid)]
            (out / car_key(year, num, rid)).write_text(car_trim(doc))
            for did, _ in parse_car_page(doc).drivers:
                if did not in done_drivers:
                    done_drivers.add(did)
                    (out / driver_key(year, did)).write_text(driver_trim(docs[driver_key(year, did)]))
        print("captured race", rid)


if __name__ == "__main__":
    {"formula1": f1, "fia_wec": wec, "gtwc_entries": gtwc_entries, "wec_entries": wec_entries}[sys.argv[1]](
        int(sys.argv[2]) if len(sys.argv) > 2 else 2026)
