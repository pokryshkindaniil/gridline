"""Build the team / manufacturer logo registry from Wikimedia Commons.

Writes
  apps/web/public/assets/logos/teams/<team-slug>.<ext>
  apps/web/public/assets/logos/manufacturers/<manufacturer-slug>.<ext>
  apps/web/lib/media-manifest.json          (the registry the UI and `gridline media-coverage` read)
  apps/web/public/assets/NOTICE.md          (human-readable provenance, generated from the registry)

Source order of preference (see README → "Team identity media"): official media kits with explicit press/reuse
terms, then official brand assets whose use for identification is permitted, then Wikimedia Commons files with a
clear reusable *copyright* status, then nothing (the UI falls back to text). No official media kit was reachable
without scraping or accepting terms on the user's behalf, so every asset below is from Commons.

Each Commons file's metadata is re-read on every run and the licence must be on the allow-list; anything else
aborts the build. Files are stored UNMODIFIED. Copyright status says nothing about trademark rights: every
record carries a trademark note.

    python scripts/media/build_team_media.py          # needs network
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "apps/web/public/assets"
LOGOS = ASSETS / "logos"
MANIFEST = ROOT / "apps/web/lib/media-manifest.json"
UA = {"User-Agent": "GRIDLINE-media/0.3 (private development; team and series media research)"}
OK_LICENSES = ("CC0", "Public domain", "CC BY")  # prefix match on Commons LicenseShortName
TRADEMARK = (
    "Copyright status only: the mark itself remains a trademark of its owner. Used solely to identify the "
    "team/manufacturer; GRIDLINE is not affiliated with or endorsed by it."
)

# team slug (as stored in teams.slug) -> Commons file. `series` = the championships whose team of that slug the logo is
# for: a team slug is only unique within a series, so a logo is never applied to a same-named team elsewhere.
TEAM_LOGOS: dict[str, dict] = {
    "af-corse": dict(series=['fia-wec', 'gt-world-challenge-europe'], name="AF Corse", file="File:AFCorseLogo.png",
                     note="Used for the entries named exactly 'AF Corse' (WEC and GTWC). Sponsor-titled entries such as 'Vista AF Corse' have their own branding and get no logo."),
    "alpine": dict(series=['formula-1'], name="Alpine", file="File:Alpine F1 Team Logo.svg",
                   note="Alpine F1 Team logo from the team's press kit (as quoted on Commons); the team's 2025 refresh is not on Commons under a clear status. Not the Alpine road-car brand mark."),
    "audi": dict(series=['formula-1'], name="Audi", file="File:Audif1.com logo17.svg", note="Audi Revolut F1 Team logo (audif1.com). Not the Audi rings."),
    "genesis-magma-racing": dict(series=['fia-wec'], name="Genesis Magma Racing", file="File:GenesisMagmaRacingLogo.png"),
    "haas-f1-team": dict(series=['formula-1'], name="Haas F1 Team", file="File:Haas F1 Team Logo.svg"),
    "mclaren": dict(series=['formula-1'], name="McLaren", file="File:McLaren Racing logo.png"),
    "mercedes": dict(series=['formula-1'], name="Mercedes", file="File:Mercedes-AMG Petronas F1 Team logo (2026).svg",
                     note="Mercedes-AMG PETRONAS F1 Team logo, 2026 edition (source quoted on Commons: team shop). Not the Mercedes-Benz star."),
    "rowe-racing": dict(series=['gt-world-challenge-europe'], name="Rowe Racing", file="File:Roweracing logo.gif",
                        note="Older ROWE Racing logo (400 px GIF, PD-textlogo). A newer CC BY-SA logo exists but was uploaded by a third party, so it is not used."),
    "toyota-gazoo-racing": dict(series=['fia-wec'], name="Toyota Gazoo Racing", file="File:Toyota Gazoo Racing stacked logo.svg"),
    "toyota-racing": dict(series=['fia-wec'], 
        name="Toyota Racing", file="File:Toyota Gazoo Racing logo.svg",
        note="Toyota Gazoo Racing logo, used for the WEC team entered as 'Toyota Racing'.",
    ),
    "williams": dict(series=['formula-1'], name="Williams", file="File:Atlassian Williams F1 Team logo.svg"),
}

# manufacturer slug (slugify(vehicle_entries.manufacturer)) -> display name, extra slugs, Commons file
MANUFACTURER_LOGOS: dict[str, dict] = {
    "alpine": dict(name="Alpine", file="File:Alpine logo.png"),
    "aston-martin": dict(name="Aston Martin", file="File:Aston Martin wordmark.svg"),
    "audi": dict(name="Audi", file="File:Audi-Logo 2016.svg"),
    "bmw": dict(name="BMW", file="File:BMW.svg"),
    "cadillac": dict(name="Cadillac", file="File:Cadillac Wordmark.svg"),
    "ferrari": dict(name="Ferrari", file="File:Ferrari wordmark.svg"),
    "ford": dict(name="Ford", file="File:Ford logo flat.svg"),
    "lamborghini": dict(name="Lamborghini", file="File:Lamborghini logo.svg"),
    "lexus": dict(name="Lexus", file="File:Lexus.svg"),
    "mclaren": dict(name="McLaren", file="File:McLaren Speedmark.svg"),
    "mercedes": dict(name="Mercedes-Benz", aliases=["mercedes-benz"], file="File:Mercedes-Benz Logo 2010.svg"),
    "mercedes-amg": dict(name="Mercedes-AMG", file="File:AMG logo.svg"),
    "peugeot": dict(name="Peugeot", file="File:Peugeot logo.svg"),
    "porsche": dict(name="Porsche", file="File:Porsche wordmark.svg"),
    "toyota": dict(name="Toyota", file="File:Toyota.svg"),
}

# Series discovery cards (/series): one deliberate, curated photograph per public championship. Photos need attribution,
# so CC BY / CC BY-SA are accepted here (never for logos); the file is Commons' own 1600 px thumbnail of the original.
HERO_WIDTH = 1600
SERIES: dict[str, dict] = {
    "formula-1": dict(
        name="Formula 1", descriptor="Single-seater", accent=None, focus="50% 62%",
        file="File:Ferrari SF-26 - Charles Leclerc approaches Spoon Curve at Suzuka during the 2026 Japanese GP (55194289242).jpg",
        alt="A 2026 Formula 1 car at speed at Suzuka, 2026 Japanese Grand Prix",
        note="2026 season car at Suzuka. Chosen as a representative current-season race photograph, not as an endorsement of one team."),
    "fia-wec": dict(
        name="FIA World Endurance Championship", descriptor="Hypercar · LMGT3", accent=None, focus="50% 55%",
        file="File:2026 6 Hours of Spa-Francorchamps Ferrari AF Corse Ferrari 499P No.50 (DSC01522).jpg",
        alt="A Hypercar at the 2026 6 Hours of Spa-Francorchamps",
        note="Hypercar at the 2026 6 Hours of Spa-Francorchamps (a WEC round)."),
    "gt-world-challenge-europe": dict(
        name="GT World Challenge Europe", descriptor="Sprint Cup · Endurance Cup", accent=None, focus="50% 55%",
        file="File:GT World Challenge Europe 2024 Nürburg Nr. 48 Auer, Engel, Morad (1).jpg",
        alt="A GT3 car at the 2024 GT World Challenge Europe round at the Nürburgring",
        note="GT3 car at the 2024 Nürburgring round (Endurance Cup); the most recent clearly licensed GTWC-round photograph found on Commons."),
}

# Investigated and NOT used (kept so nobody repeats the search). entity -> reason
REJECTED: dict[str, dict[str, str]] = {
    "manufacturers": {
        "corvette": "Only CC BY-SA uploads by third parties (photos / a re-drawn emblem); the Chevrolet bowtie is not the Corvette mark.",
        "red-bull": "Dropped: the only file is the Red Bull drinks brand logo, which is not the Red Bull Racing team identity (F1 manufacturer is 'Red Bull Racing').",
        "genesis": "Only a CC BY-SA re-drawing by a third-party uploader; copyright status of the underlying logo is unclear.",
    },
    "teams": {
        "ferrari": "No clearly reusable Scuderia Ferrari team logo on Commons: the only hit is a fan-made 'own work' image; the prancing horse is not offered under a free licence.",
        "red-bull-racing": "Only an outdated 2005 logo (unknown author) on Commons.",
        "racing-bulls": "Nothing on Commons for the current team (only Red Bull Racing / AlphaTauri-era material of unclear status).",
        "aston-martin": "Only a CC BY upload of unknown authorship (2024 F1 team logo).",
        "cadillac": "Only a CC0 PNG 'own work' by a third-party uploader (a logo they do not own): rights-holder status unverified.",
        "team-wrt": "Only a CC BY-SA JPEG uploaded by a third party; rights-holder status unverified.",
        "peugeot-totalenergies": "Only a CC BY-SA upload of unknown authorship.",
        "tf-sport": "Only a CC BY-SA PNG 'own work' by a third party.",
        "racing-spirit-of-leman": "Only a CC BY-SA PNG by a third party.",
        "proton-competition": "A 'PD-logo' PNG screenshotted from the SRO website, not published by the team: status unclear.",
        "high-class-racing": "Only CC BY-SA PNGs uploaded by a third party.",
        "paradine-competition": "Only a CC BY 4.0 SVG 'own work' by a third party (a logo they do not own).",
        "cadillac-hertz-team-jota": "Only a 200 px JPG of the 'Jota Sport' mark, a different branding from the entry name.",
        "(all other WEC / GTWC teams)": "No logo found on Commons. Official media kits were not used (would need scraping or accepting terms).",
    },
}


def api(**p):
    p["format"] = "json"
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(p)
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30))


def get(url: str) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()


def strip(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


def meta(title: str, *, hero: bool = False, thumb: int | None = None) -> dict:
    extra = {"iiurlwidth": thumb} if thumb else {}
    r = api(action="query", titles=title, prop="imageinfo", iiprop="url|size|mime|extmetadata", **extra)
    page = next(iter(r["query"]["pages"].values()))
    if "imageinfo" not in page:
        sys.exit(f"MISSING {title}")
    ii = page["imageinfo"][0]
    m = ii["extmetadata"]
    g = lambda k: strip(m.get(k, {}).get("value", ""))  # noqa: E731
    lic = g("LicenseShortName")
    if not lic.startswith(OK_LICENSES) or (not hero and lic.startswith("CC BY-SA")):  # logos: no share-alike
        sys.exit(f"REFUSING {title}: licence {lic!r} is not on the allow-list")
    author = g("Artist") or "Unknown"
    author = re.sub(r"(Unknown author)+", "Unknown author", author)
    return dict(
        page="https://commons.wikimedia.org/wiki/" + page["title"].replace(" ", "_"),
        original=ii["url"], mime=ii["mime"], width=ii["width"], height=ii["height"], thumb=ii.get("thumburl"),
        thumb_width=ii.get("thumbwidth"), thumb_height=ii.get("thumbheight"),
        author=author, license=lic, licenseUrl=g("LicenseUrl") or None,
    )


EXT = {"image/svg+xml": ".svg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif", "image/jpeg": ".jpg"}


def fetch(kind: str, slug: str, name: str, spec: dict) -> dict:
    """kind = 'team' | 'manufacturer'. Downloads the file unmodified and returns its registry record."""
    m = meta(spec["file"])
    folder = LOGOS / f"{kind}s"
    folder.mkdir(parents=True, exist_ok=True)
    rel = f"{slug}{EXT[m['mime']]}"
    (folder / rel).write_bytes(get(m["original"]))
    by = m["license"].startswith("CC BY")
    return dict(
        entity=slug,
        assetType=f"{kind}-logo",
        src=f"/assets/logos/{kind}s/{rel}",
        alt=f"{name} logo",
        width=m["width"], height=m["height"],
        sourcePage=m["page"],
        originalUrl=m["original"],
        license=m["license"],
        licenseUrl=m["licenseUrl"],
        author=m["author"],
        attribution=f"{m['author']} · {m['license']} · {m['page']}" if by else None,
        retrieved=str(date.today()),
        modifications="none (original file)",
        notes=spec.get("note", ""),
        trademarkNote=TRADEMARK,
    )


def fetch_hero(slug: str, spec: dict) -> dict:
    m = meta(spec["file"], hero=True, thumb=HERO_WIDTH)
    folder = ASSETS / "series"
    folder.mkdir(parents=True, exist_ok=True)
    rel = f"{slug}-hero.jpg"
    (folder / rel).write_bytes(get(m["thumb"]))
    return dict(
        entity=slug, assetType="series-hero", src=f"/assets/series/{rel}", alt=spec["alt"],
        width=m["thumb_width"], height=m["thumb_height"], focus=spec.get("focus"),
        sourcePage=m["page"], originalUrl=m["original"], license=m["license"], licenseUrl=m["licenseUrl"],
        author=m["author"], attribution=m["author"],
        retrieved=str(date.today()),
        modifications=f"resized to {m['thumb_width']} px wide (Wikimedia Commons thumbnail); cropped on screen with CSS object-position only",
        notes=spec.get("note", ""),
    )


def write_notice(reg: dict) -> None:
    L = [
        "# Team & manufacturer logos: sources, licences, attribution", "",
        "_Generated by `scripts/media/build_team_media.py` from `apps/web/lib/media-manifest.json` — do not edit by hand._", "",
        reg["policy"], "",
        "**Legal status in one paragraph.** Every file below is hosted on Wikimedia Commons with a licence tag that makes the "
        "*copyright* in the artwork reusable (public domain / CC0 — typically because the logo is a simple text or geometric mark). "
        "That says nothing about *trademark* rights: all names and logos remain the property of their owners, are used only to "
        "identify the team or manufacturer, and GRIDLINE is not affiliated with, sponsored or endorsed by any of them. "
        "Commons licence tags are uploader/community assessments, not warranties; none of these files was obtained from an official "
        "media kit. Before any commercial use, obtain permission or official press assets from each rights holder.", "",
    ]
    for key, title in (("teams", "Team logos"), ("manufacturers", "Manufacturer logos")):
        L += [f"## {title} ({len(reg[key])})", "",
              "| Entity | Licence | Author (as on Commons) | Source page | Retrieved | Notes |", "|---|---|---|---|---|---|"]
        for slug, e in sorted(reg[key].items()):
            a = e["logo"]
            lic = f"[{a['license']}]({a['licenseUrl']})" if a.get("licenseUrl") else a["license"]
            L.append(f"| `{slug}` ({e['name']}) | {lic} | {a['author']} | <{a['sourcePage']}> | {a['retrieved']} | {a['notes'] or '—'} |")
        L.append("")
    L += [f"## Series hero photographs ({len(reg['series'])})", "",
          "Photographs shown on `/series`. Unlike the logos they are CC BY / CC BY-SA *photographs*: attribution is shown on the card, "
          "and the 1600 px files below are resized copies, so they remain under their original licence (not GRIDLINE's).", "",
          "| Series | Licence | Photographer | Source page | Retrieved | Modifications |", "|---|---|---|---|---|---|"]
    for slug, e in sorted(reg["series"].items()):
        a = e["hero"]
        lic = f"[{a['license']}]({a['licenseUrl']})" if a.get("licenseUrl") else a["license"]
        L.append(f"| `{slug}` ({e['name']}) | {lic} | {a['author']} | <{a['sourcePage']}> | {a['retrieved']} | {a['modifications']} |")
    L.append("")
    L += ["## Investigated and not used", ""]
    for key in ("manufacturers", "teams"):
        for slug, why in reg["rejected"][key].items():
            L.append(f"- **{key[:-1]} {slug}:** {why}")
    L += ["", "Logo files are stored exactly as downloaded (no modification). `attribution` is filled only where a licence requires it (CC BY).", ""]
    (ASSETS / "NOTICE.md").write_text("\n".join(L))


def build() -> None:
    if LOGOS.exists():
        shutil.rmtree(LOGOS)
    reg: dict = dict(
        version=3,
        policy=(
            "Team/manufacturer logos only (no car photography on team rows); one curated hero photograph per public series for /series. Sources in order of preference: official media kits with explicit reuse terms; official "
            "brand assets whose use for identification is permitted; Wikimedia Commons files with a clear reusable copyright status; "
            "otherwise no asset (the UI shows a typeset name). Registry keys are team slugs (teams.slug) and manufacturer slugs "
            "(slugify of vehicle_entries.manufacturer); API-provided URLs (teams.logo_url, vehicle_entries.fallback_logo_url) win."
        ),
        teams={}, manufacturers={}, series={}, rejected=REJECTED,
    )
    for slug, spec in TEAM_LOGOS.items():
        reg["teams"][slug] = dict(name=spec["name"], series=spec["series"], logo=fetch("team", slug, spec["name"], spec))
    for slug, spec in MANUFACTURER_LOGOS.items():
        reg["manufacturers"][slug] = dict(name=spec["name"], aliases=spec.get("aliases", []), logo=fetch("manufacturer", slug, spec["name"], spec))
    if (ASSETS / "series").exists():
        shutil.rmtree(ASSETS / "series")
    for slug, spec in SERIES.items():
        reg["series"][slug] = dict(name=spec["name"], descriptor=spec["descriptor"], accent=spec["accent"],
                                   logo=None, hero=fetch_hero(slug, spec))
    MANIFEST.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n")
    write_notice(reg)
    print(f"built {len(reg['teams'])} team logos, {len(reg['manufacturers'])} manufacturer logos, {len(reg['series'])} series heroes")


if __name__ == "__main__":
    build()
