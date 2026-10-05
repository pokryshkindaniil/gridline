PY := apps/api/.venv/bin/python
.PHONY: db install migrate seed sync media-coverage scheduler api web test lint up down dev-up dev-down dev-status dev-logs

db:        ## start PostgreSQL (Docker)
	docker compose up -d db

install:   ## python venv + node deps
	python3 -m venv apps/api/.venv
	apps/api/.venv/bin/pip install -e packages/shared -e packages/calendar -e packages/sources -e "apps/api[dev]"
	cd apps/web && npm install

migrate:
	cd apps/api && .venv/bin/alembic upgrade head

seed:      ## DEV ONLY: fixtures through the sync engine + sample roster
	cd apps/api && .venv/bin/gridline seed

sync:      ## live sync of every adapter that has a live source
	cd apps/api && .venv/bin/gridline sync all

media-coverage: ## teams in the DB vs the logo registry (apps/web/lib/media-manifest.json)
	cd apps/api && .venv/bin/gridline media-coverage

scheduler: ## periodic sync loop (every SYNC_INTERVAL_MINUTES)
	cd apps/api && .venv/bin/gridline scheduler

api:
	cd apps/api && .venv/bin/uvicorn app.main:app --reload --port 8000

web:
	cd apps/web && npm run dev

test:
	cd apps/api && .venv/bin/pytest
	cd apps/web && npm test

lint:
	cd apps/api && .venv/bin/ruff check . && .venv/bin/ruff check ../../packages --config pyproject.toml
	cd apps/web && npm run lint

up:        ## full stack in Docker
	docker compose up --build

down:
	docker compose down

# ---- background local dev (nohup + PID files in .tmp/; returns immediately) ----
dev-up:      ## ensure DB, start API (:8000) and web (:3000) in the background if not already running
	@scripts/dev.sh up

dev-down:    ## stop only the processes dev-up started (DB is left running)
	@scripts/dev.sh down

dev-status:  ## DB / API / web status, ports, PIDs
	@scripts/dev.sh status

dev-logs:    ## tail .tmp/api.log and .tmp/web.log
	@scripts/dev.sh logs
