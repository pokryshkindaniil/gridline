# Sources and provenance

GRIDLINE uses official championship or organizer sources. Each stored schedule or entry record carries its source name and URL where available. The UI exposes verification time and source health rather than hiding stale data.

## Formula 1

The Formula 1 adapter reads the season index and individual race pages from formula1.com. Session times come from `SportsEvent` JSON-LD; embedded page data supplies the IANA timezone and offset used for validation. The season roster also comes from formula1.com.

Likely failures include markup changes, unavailable race pages, and previously unseen timezone aliases. Affected events are quarantined instead of replacing valid data.

## FIA WEC

The WEC adapter follows season and race pages to official calendar files. ICS UIDs provide stable session identity. Local times use the published `TZID`; UTC-only files use a maintained circuit timezone map.

The official ICS file is authoritative when page timestamps disagree. Missing calendar links, invalid calendar data, and unknown circuit timezones quarantine the event.

Entry lists come from official event pages. Older settled events with live entry data are not fetched on every cycle.

## GT World Challenge Europe

The GTWC Europe adapter reads official SRO calendar and event timetable pages. It compares local and GMT columns and maps venue countries to IANA timezones. Entry lists also come from official SRO pages.

Markup changes and unmapped countries fail loudly. Test and prologue events remain classified as test sessions.

## IMSA

IMSA remains fixture-only and is not visible in the public product. The available official pages and PDFs are not a dependable or clearly permitted automated source: access varies behind a managed challenge, and the applicable terms restrict automated collection and redistribution.

The adapter, fixtures, tests, and data model remain in the repository for future work. Public support requires written permission or a suitable official feed. Development fixtures are labeled as synthetic data and cannot be loaded in production mode.

## Fixtures

F1, WEC, and GTWC fixtures are trimmed captures of official pages. Fixture mode is intended for deterministic tests and local development. Source labels distinguish fixtures from live data throughout the application.

Refresh scripts live under `packages/sources/scripts` and `scripts/`. Review captured data before committing it, and do not include credentials or personal data.

## Adding a source

A new public source should provide:

- stable event and session identifiers
- explicit timezone information or a maintainable circuit mapping
- clear permission for automated use and redistribution
- parser fixtures and failure-mode tests
- provenance labels and health reporting

Adapters should remain pure: fetching and parsing belong in `packages/sources`; database writes belong in `apps/api`.
