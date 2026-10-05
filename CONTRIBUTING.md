# Contributing to GRIDLINE

GRIDLINE is developed in public. Focused bug reports and pull requests are welcome; please open an issue before starting a large change.

The most valuable contribution will be a **new championship adapter** or a **better source for an existing one**.

## Ground rules

- **Provenance first.** Prefer an official organiser source. Prefer structured data (JSON, iCal, JSON-LD) over HTML, and HTML over browser automation.
- **Respect access controls.** No bot-protection bypassing, no login walls, no ignoring `robots.txt`/terms. If a site blocks automated access, document that in the adapter's `limitation` and ship a clearly-labelled fixture instead.
- **Never fake it.** An adapter that cannot fetch live data must say so (`live = False`). Synthetic fixtures must carry `fixture_label = "synthetic dev fixture"`. Never label fixture data as live.
- **Fail loudly, fail small.** `parse()` returns `ParseResult(sessions, issues)`. A problem confined to one event (bad markup, unknown timezone, missing calendar link) becomes a `SourceIssue` — that event is quarantined and stored data for it is left untouched. Raise `SourceError` only when the whole payload is unusable. The sync engine refuses empty/suspiciously small results.
- **No timezone guessing.** The circuit IANA zone must come from the source or a maintained mapping; if neither knows it, quarantine the event. Never default to UTC. `ParsedSession` rejects invalid zones.
- **UTC everywhere.** `ParsedSession.start_at` must be timezone-aware; the circuit's IANA zone goes in `timezone`.
- **Stable identity.** `external_id` identifies a session *within an event* and must never contain a time. Renaming or moving a session must not change it. `event_external_id` must be stable per event per season.

## Add a new championship (example: Super GT)

1. **Create the package**: `packages/sources/gridline_sources/super_gt/` with `__init__.py`, `adapter.py`, `parser.py`, `fixtures/`.
2. **Implement the adapter** (`adapter.py`) by subclassing `MotorsportSource`:
   ```python
   class SuperGtSource(MotorsportSource):
       def __init__(self):
           self.source_id = "super_gt"            # CLI name
           self.series_slug = "super-gt"          # must exist in app/catalog.py
           self.source_name = "Super GT (GTA)"    # shown to users
           self.official_url = "https://supergt.net/en/race/schedule"
           self.fixture_dir = Path(__file__).parent / "fixtures"
       async def fetch(self) -> RawSchedule: ...   # httpx only; use base.http_client()
       def parse(self, raw) -> ParseResult: ...    # pure function: sessions + per-event issues
   ```
3. **Capture fixtures.** Save the *raw* payloads you parse (trim bulky HTML but keep its structure) into `fixtures/` — see `packages/sources/scripts/capture_fixtures.py` for examples. `load_fixture()` feeds them to `parse()` untouched. Fixtures must be real captures unless the source is unreachable, in which case say `synthetic`.
4. **Write parser tests** in `apps/api/tests/test_parsers.py` (or a new file): assert exact UTC instants for a few sessions, session types, timezone, identity uniqueness — and reliability cases: malformed page → issue (not crash), unknown timezone → quarantined, 5xx/timeout via `httpx.MockTransport` (`adapter.transport`; see `tests/test_http_adapters.py`).
5. **Register it** in `gridline_sources/registry.py`, add the series to `SERIES_CATALOG` in `apps/api/app/catalog.py` (set `active=True`), and add the package to `packages/sources/pyproject.toml`.
6. **Try it:**
   ```bash
   cd apps/api
   python -m app.sources.sync super_gt --fixtures   # offline
   python -m app.sources.sync super_gt              # live
   ```
7. **Optional capability — entry lists.** If the official source publishes who is entered at each event, also provide `fetch_entries / parse_entries / load_entries_fixture` (see `gridline_sources/entries.py`; fixtures in `<id>/entry_fixtures/`, capture via `scripts/capture_fixtures.py`). Report per-event problems as `SourceIssue`s so only that event is quarantined. Do not implement a capability your source has no data for.
8. **Update the README** table of sources (real vs fixture, known limitations) and open a PR.

## Development workflow

```bash
make db install migrate seed
make api      # terminal 1
make web      # terminal 2
make test lint
```

Backend style: `ruff check` (config in `apps/api/pyproject.toml`), typed Python 3.12+. Frontend: `npm run lint` (tsc), `npm test`, `npm run build`. CI runs all of this plus an Alembic up/check/down/up cycle on a fresh Postgres.

ICS output is protected by golden files in `apps/api/tests/golden/`; if you change rendering on purpose, regenerate with `UPDATE_GOLDEN=1 pytest tests/test_ics_golden.py` and review the diff against RFC 5545.

Schema changes need an Alembic migration: `cd apps/api && alembic revision --autogenerate -m "what changed"` — then read the generated file.

## Pull requests

Keep PRs focused. Include tests for parsers and any change to the sync/diff or ICS behaviour. By contributing you agree your work is licensed under AGPL-3.0-or-later.

## Identity, aliases and media (teams, drivers, cars)

- **Canonical entities, source spellings in provenance.** Teams, drivers, manufacturers and vehicle models are resolved through `apps/api/app/services/identity.py`; never create them by hand-rolled slug lookups in an importer. An adapter reports exact source spellings (and the source's own ids where it has them: `ParsedDriver.external_id`, `ParsedEntry.team_external_id`).
- **Never merge by similarity.** Two spellings become one entity only through an explicit entry in `packages/shared/gridline_shared/aliases.py` (source + exact variant → canonical, with the reason). Run `gridline identity-report` to find candidates; confirm one against a source before adding it. Add a test that the alias applies to its own source only.
- **Manufacturer ≠ vehicle model.** `Ferrari` is the manufacturer, `SF-26` the model. If a source does not state the model, leave it `None`: the UI shows the manufacturer only.
- **Logos.** Only add a team logo with a clear *copyright* status (Commons `PD-textlogo`/CC0/PD uploaded from the team's own materials, or an official asset with explicit permission) and record where it came from. A manufacturer wordmark is never a team logo. Add it to `scripts/media/build_team_media.py` with the series it is for, rebuild, run `gridline media-coverage`.
- **Series visuals** (hero photographs) live in the same media registry with full provenance; components never hard-code asset URLs.
- A series that must not be public yet is switched off with `public=False` in `app/catalog.py`; do not special-case slugs.
