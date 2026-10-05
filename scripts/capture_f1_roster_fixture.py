"""Capture the live formula1.com roster pages into the (trimmed) offline fixture used by `gridline seed` and tests.

    apps/api/.venv/bin/python scripts/capture_f1_roster_fixture.py

Pages are reduced by `roster.trim_document` to the elements the parser reads, so the fixture stays small.
"""
import asyncio
import shutil
from pathlib import Path

from gridline_sources.formula1.adapter import Formula1Source
from gridline_sources.formula1.roster import trim_document

OUT = Path(__file__).resolve().parents[1] / "packages/sources/gridline_sources/formula1/fixtures_roster"


async def main() -> None:
    src = Formula1Source()
    raw = await src.fetch_entries(None)  # type: ignore[arg-type]
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    for key, html in sorted(raw.documents.items()):
        (OUT / key).write_text(trim_document(key, html), encoding="utf-8")
    print(f"{len(raw.documents)} documents from {raw.source_url} -> {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
