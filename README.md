# GRIDLINE

GRIDLINE is a motorsport calendar that keeps subscribed events up to date when official schedules change.

**Live:** [gridline-gamma.vercel.app](https://gridline-gamma.vercel.app)

Choose championships, session types, and a timezone to create a permanent calendar URL for Apple Calendar, Google Calendar, Outlook, or any other iCalendar client. Schedule changes update the existing event instead of creating a duplicate.

GRIDLINE is deployed on Vercel, backed by Neon Postgres, and maintained by GitHub Actions.

## Championships

| Championship | Schedule source | Entries |
| --- | --- | --- |
| Formula 1 | formula1.com | season roster from formula1.com |
| FIA WEC | fiawec.com and official ICS feeds | event entry lists from fiawec.com |
| GT World Challenge Europe | SRO | event entry lists from SRO |

IMSA support remains fixture-only and is intentionally hidden from the public product. Its official site is not currently suitable for reliable automated ingestion and redistribution.

## What the product does

- Tracks individual sessions rather than only race weekends.
- Keeps stable session and calendar identities when times change.
- Records schedule changes and exposes source freshness.
- Publishes revocable iCalendar feeds with ETag support.
- Shows teams, drivers, cars, and source provenance where official data is available.

## Architecture

```text
official sources
      │
      ▼
packages/sources ──► apps/api ──► Neon Postgres
                         │
                         ├──► calendar feeds
                         └──► apps/web
                                  │
                                  ▼
                                Vercel
```

- `apps/api`: FastAPI, SQLAlchemy, and Alembic
- `apps/web`: Next.js App Router
- `packages/sources`: source adapters and parsers
- `packages/calendar`: iCalendar rendering
- `packages/shared`: shared identity and classification helpers

See [Architecture](docs/ARCHITECTURE.md) for sync, identity, calendar, and safety details.

## Local development

Requirements: Python 3.12+, Node.js 22+, Docker, and PostgreSQL 16+.

```bash
cp .env.example .env
make db install migrate
make sync
make api
make web
```

The web app runs at <http://localhost:3000>; API documentation is available at <http://localhost:8000/docs>.

To run the full stack in containers:

```bash
docker compose up --build
```

Fixture loading is for development only and is rejected when `ENVIRONMENT=production`.

## Quality checks

```bash
make test
make lint

cd apps/web
npm test
npm run typecheck
npm run build
```

Backend tests require `TEST_DATABASE_URL` to point to a disposable database. The suite recreates its `public` schema.

## Operations

Production uses:

- Vercel for the Next.js application and FastAPI service
- Neon for PostgreSQL
- GitHub Actions for migrations and scheduled source syncs

Deployment configuration, required environment variables, smoke checks, and recovery steps are documented in [Deployment](docs/DEPLOYMENT.md). Do not use fixture mode against production.

Useful commands:

```bash
gridline sync all
gridline scheduler --once
gridline identity-report
gridline media-coverage
```

## Documentation

- [Architecture and data model](docs/ARCHITECTURE.md)
- [Source adapters and provenance](docs/SOURCES.md)
- [Deployment and operations](docs/DEPLOYMENT.md)
- [Contributing](CONTRIBUTING.md)

## Known limitations

- The rate limiter is process-local. Multi-instance deployment needs a shared limiter.
- Source adapters depend on upstream HTML and calendar formats and can require maintenance when those sites change.
- IMSA is not publicly enabled pending a reliable, permitted source.
- Team and vehicle media coverage is incomplete; missing assets fall back to text.

## License

AGPL-3.0-or-later. See [LICENSE](LICENSE). Third-party material and trademarks are documented in [NOTICE](NOTICE); media-specific attribution is in [apps/web/public/assets/NOTICE.md](apps/web/public/assets/NOTICE.md).
