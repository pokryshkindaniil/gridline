# Architecture

GRIDLINE ingests official motorsport schedules, stores normalized sessions, and publishes them through a web application, JSON API, and iCalendar feeds.

## Data flow

Each source adapter fetches upstream data and parses it into normalized records. Source packages do not access the database. The API owns persistence, change detection, health reporting, and feed delivery.

```text
fetch → parse → validate → compare → persist → publish
```

Schedule syncs run in three phases so database transactions are not held open during network requests:

1. Create the run record and read the state needed for validation.
2. Fetch and parse without an open database session.
3. Open a fresh session, apply changes, and finish the run record.

Sources run independently. A failure in one championship does not prevent the others from updating.

## Safety rules

Sync favors preserving known-good data over accepting suspicious input.

- Empty schedule results fail without changing stored sessions.
- Results below `SYNC_MIN_RATIO` of the previous successful run fail.
- Parser issues quarantine the affected event while valid events continue.
- A sharp session-count drop within one event suppresses cancellations for that event.
- Missing future sessions are marked cancelled, never deleted.
- Unknown circuit timezones quarantine the event; there is no UTC fallback.

Every attempt creates a `SourceRun` with its mode, status, counts, duration, and issues. Fixture provenance is kept distinct from live provenance.

## Concurrency

A database-backed lease prevents overlapping syncs across schedulers, Actions jobs, and manual runs. The lease is acquired atomically and renewed with short transactions. If heartbeats stop, it expires and another runner can take over.

The database clock is authoritative, avoiding clock-skew disagreements between runners. Losing lease ownership cancels the active run before it can continue writing.

## Identity and changes

An event is identified by season and upstream event ID. A session is identified by event and upstream session ID. Start time is not part of identity, so rescheduling updates the existing record and calendar UID.

Changes to schedule fields create `SessionChange` records and increment the session sequence. Canonical drivers, teams, manufacturers, and vehicle models are resolved through explicit source aliases; fuzzy matching is intentionally avoided.

Series visibility is controlled by `Series.public`. Hidden series retain adapters, fixtures, and stored data but do not appear in public listings and cannot be added to feeds.

## Calendar feeds

Feed creation returns separate public and edit tokens. Only the public token appears in the subscription URL. Edit tokens are returned once, stored as SHA-256 hashes, and accepted through `X-Edit-Token` for mutations.

Calendar events use stable UIDs, UTC timestamps, revision sequences, and cancellation status. The selected timezone affects calendar metadata and human-readable descriptions; clients render the UTC instant in the viewer's local zone.

## Health and logging

`/health` reports application and database availability. `/sources/health` reports upstream freshness and failures. Keeping these separate prevents a source outage from presenting as an API outage.

Logs are JSON lines. Request logs include the method, path, status, and duration, but never query strings, headers, or tokens. Sync logs include identifiers, counters, status, and timing.

## Repository layout

```text
apps/api/          FastAPI application, models, services, and tests
apps/web/          Next.js application and tests
packages/sources/  source adapters, parsers, and fixtures
packages/calendar/ iCalendar renderer
packages/shared/   shared enums, names, and identity helpers
migrations/        Alembic migrations
docs/              operational and technical documentation
```
