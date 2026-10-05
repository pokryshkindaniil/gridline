#!/bin/sh
# API container: wait for Postgres, apply migrations, then serve.
set -eu
python -m app.wait_for_db
alembic upgrade head
# canonical identities for data imported before they existed (curated aliases, manufacturers, models); idempotent
python -m app.cli identity-apply || echo "identity-apply skipped"
# --no-access-log: the app writes its own structured request log (path only, never query strings)
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log --proxy-headers --forwarded-allow-ips='*'
