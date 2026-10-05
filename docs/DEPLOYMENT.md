# Deployment: Vercel (web + api) + Neon + GitHub Actions

```
Internet → Vercel ─┬─ web (Next.js, apps/web)   /*
                   └─ api (FastAPI, apps/api)   /api and /api/*     web ──binding API_URL──▶ api
                                   │
                                   ▼
                            Neon PostgreSQL  ◀── GitHub Actions (migrate + sync every 6 h)
```

Only `web` and `api` are Vercel services. `packages/{shared,calendar,sources}` are Python libraries installed into `api`
(`installCommand` in `vercel.json`), not services. Vercel forwards the **original** path to a service, so the API serves
`/api/*` itself (`root_path="/api"`); unprefixed paths still work for local dev and Docker.

## 1. Neon
- Project branch `production`, database `gridline`, role `neondb_owner`. Do not reset it.
- Two URLs, both `postgresql+psycopg://…` (psycopg3), `?sslmode=require`:
  - **pooled** (`-pooler` host) → Vercel `api` (many short serverless connections);
  - **direct** (no `-pooler`) → migrations and syncs (long runs; the sync lease itself needs no persistent connection).
- Do not change `idle_in_transaction_session_timeout`: the sync is written so no transaction is open during network IO.

## 2. Vercel environment variables (Project → Settings → Environment Variables, Production)
| Variable | Value |
| --- | --- |
| `DATABASE_URL` | Neon **pooled** URL |
| `ENVIRONMENT` | `production` |
| `PUBLIC_API_BASE_URL` | `https://<production-domain>/api` (calendar links become `…/api/calendar/<token>.ics`) |
| `CORS_ORIGINS` | `https://<production-domain>` |
| `TRUST_PROXY_HEADERS` | `true` (rate limiting then keys on the right-most `X-Forwarded-For` entry, which Vercel sets) |

Never set `API_URL` (injected by the `web → api` binding at runtime). Production refuses to start with a missing/local
`DATABASE_URL`, wildcard `CORS_ORIGINS` or a localhost `PUBLIC_API_BASE_URL`.

## 3. GitHub (Settings → Secrets and variables → Actions)
- Secret `NEON_DIRECT_DATABASE_URL` = Neon **direct** URL.
- Variables `PUBLIC_API_BASE_URL`, `CORS_ORIGINS` (same values as above; they only satisfy production-settings validation).
- Optional: a `production` Environment (the workflow uses it) for approvals.

## 4. Migrations (also run by the workflow before every sync)
```bash
cd apps/api && DATABASE_URL='<direct url>' ENVIRONMENT=production PUBLIC_API_BASE_URL=https://<domain>/api CORS_ORIGINS=https://<domain> alembic upgrade head   # head = 0008
```

## 5. Initial production sync (live only: never `--fixtures`, never IMSA)
Either run the workflow (Actions → *production-sync* → Run workflow), or locally with the **direct** URL:
```bash
cd apps/api
export DATABASE_URL='<direct url>' ENVIRONMENT=production PUBLIC_API_BASE_URL=https://<domain>/api CORS_ORIGINS=https://<domain>
gridline sync formula1 && gridline sync fia_wec && gridline sync gt_world_challenge   # WEC entries take ~10 min
```
A failed pass is recorded in `source_runs`; re-running is safe (idempotent, no data is dropped).

## 6. Deploy
Push to the Git branch connected to the Vercel project (or `vercel --prod` after `vercel link`). Vercel builds `api` and
`web` independently; neither build needs the database or a running API (all pages are dynamic).

## 7. Smoke checks
```bash
curl -s https://<domain>/api/health            # {"status":"ok","database":"up"}
curl -s https://<domain>/api/series | head -c 300
curl -sI https://<domain>/api/docs             # 200
curl -s -o /dev/null -w '%{http_code}\n' https://<domain>/series        # 200, lists F1 / WEC / GTWC, no IMSA
curl -s https://<domain>/api/sources/health | head -c 300
```
Then create a feed on `/calendar/create`; the subscription URL must read `https://<domain>/api/calendar/<token>.ics`
and return `text/calendar`.

## 8. Rollback / recovery
- Bad deployment: Vercel → Deployments → previous good deployment → *Promote to Production* (instant; data unaffected).
- Bad migration: restore from a Neon branch/point-in-time restore taken before it; migrations are additive, `alembic downgrade -1` is available.
- Bad data: re-run the sync (it only moves data toward the official source). Source outage: the previous data stays and `/api/sources/health` shows `stale`/`failing`.
- API cannot reach the DB: check the pooled URL and Neon endpoint status; `/api/health` answers 503 when the database is down.

## 9. Trigger a sync manually
GitHub → Actions → *production-sync* → *Run workflow*, or `gh workflow run production-sync.yml` and `gh run watch`.
Schedule: every 6 hours (`17 */6 * * *` UTC); runs never overlap (concurrency group + the `sync_leases` database lease: heartbeat 60 s, TTL 300 s, auto-recovers after a crash).
