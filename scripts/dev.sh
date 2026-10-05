#!/usr/bin/env bash
# Lightweight local dev runner (macOS/Linux). No process manager: nohup + PID files + logs in .tmp/.
#   scripts/dev.sh up | down | status | logs
#
# - DB:  uses a reachable local Postgres on :5432 (creates the `gridline` database if missing),
#        otherwise starts the compose `db` service. Override with DATABASE_URL.
# - API: http://127.0.0.1:8000   Web: http://127.0.0.1:3000   (override with API_PORT / WEB_PORT)
# - Reuses a healthy GRIDLINE process already on the port (and will NOT stop it on `down`);
#   a broken GRIDLINE process (cwd inside this repo) is replaced; foreign processes are never touched.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$ROOT/.tmp"; mkdir -p "$TMP"
API_PORT="${API_PORT:-8000}"; WEB_PORT="${WEB_PORT:-3000}"
API_URL_LOCAL="http://127.0.0.1:$API_PORT"; WEB_URL_LOCAL="http://127.0.0.1:$WEB_PORT"

say()  { printf '%s\n' "$*"; }
alive() { [ -n "${1:-}" ] && kill -0 "$1" 2>/dev/null; }
port_pids() { lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null | sort -u; }
pid_cwd() { lsof -p "$1" -a -d cwd -Fn 2>/dev/null | sed -n 's/^n//p'; }
is_gridline() { case "$(pid_cwd "$1")" in "$ROOT"*) return 0;; *) return 1;; esac; }
kill_tree() { local c; for c in $(pgrep -P "$1" 2>/dev/null); do kill_tree "$c"; done; kill "$1" 2>/dev/null; }
pidfile_pid() { [ -f "$TMP/$1.pid" ] && cat "$TMP/$1.pid"; }
api_healthy() { curl -fsS -m 3 "$API_URL_LOCAL/health" 2>/dev/null | grep -q '"database":"up"'; }
web_healthy() {  # page renders (200) AND its stylesheet is served (a half-built .next serves 200 HTML but 404 CSS)
  local html css
  html="$(curl -s -m 8 -w '\n%{http_code}' "$WEB_URL_LOCAL/")" || return 1
  [ "$(printf '%s' "$html" | tail -n1)" = "200" ] || return 1
  css="$(printf '%s' "$html" | grep -o '/_next/static/[^"]*\.css' | head -1)"
  [ -z "$css" ] || [ "$(curl -s -m 8 -o /dev/null -w '%{http_code}' "$WEB_URL_LOCAL$css")" = "200" ]
}
wait_for() { local fn=$1 secs=$2 i; for ((i=0;i<secs;i++)); do $fn && return 0; sleep 1; done; return 1; }

# ---------- database ----------
db_up() {
  if [ -n "${DATABASE_URL:-}" ]; then echo "$DATABASE_URL" > "$TMP/db.url"; say "db   : using DATABASE_URL"; return 0; fi
  if pg_isready -q -h localhost -p 5432 && psql -h localhost -d postgres -Atc 'select 1' >/dev/null 2>&1; then
    psql -h localhost -d postgres -Atc "select 1 from pg_database where datname='gridline'" | grep -q 1 || createdb -h localhost gridline
    echo "postgresql+psycopg://$(id -un)@localhost:5432/gridline" > "$TMP/db.url"
    say "db   : local PostgreSQL on :5432 (database 'gridline')"; return 0
  fi
  command -v docker >/dev/null 2>&1 || { say "db   : no Postgres on :5432 and docker not found"; return 1; }
  local port="${GRIDLINE_DB_PORT:-5432}"
  (cd "$ROOT" && GRIDLINE_DB_PORT="$port" docker compose up -d db >/dev/null 2>&1) || { say "db   : docker compose up db failed"; return 1; }
  for i in $(seq 1 40); do pg_isready -q -h localhost -p "$port" && break; sleep 1; done
  echo "postgresql+psycopg://gridline:${POSTGRES_PASSWORD:-gridline}@localhost:$port/gridline" > "$TMP/db.url"
  say "db   : docker compose db on :$port"
}
db_url() { cat "$TMP/db.url" 2>/dev/null; }

# ---------- api ----------
api_up() {
  local pid; pid="$(pidfile_pid api)"
  if alive "$pid" && api_healthy; then say "api  : already running (pid $pid) $API_URL_LOCAL"; return 0; fi
  for p in $(port_pids "$API_PORT"); do
    alive "$p" || continue
    if is_gridline "$p"; then
      if api_healthy; then say "api  : reusing healthy GRIDLINE API (pid $p, not managed by dev-down)"; return 0; fi
      say "api  : replacing stale GRIDLINE API on :$API_PORT (pid $p)"; kill_tree "$p"; sleep 1
    else say "api  : port $API_PORT is used by a non-GRIDLINE process (pid $p). Stop it or set API_PORT."; return 1; fi
  done
  for p in $(port_pids "$API_PORT"); do kill -9 "$p" 2>/dev/null; done
  ( cd "$ROOT/apps/api" && DATABASE_URL="$(db_url)" .venv/bin/alembic upgrade head >"$TMP/migrate.log" 2>&1 ) \
    || { say "api  : migrations failed, see .tmp/migrate.log"; return 1; }
  ( cd "$ROOT/apps/api" && DATABASE_URL="$(db_url)" PUBLIC_API_BASE_URL="$API_URL_LOCAL" \
      CORS_ORIGINS="$WEB_URL_LOCAL,http://localhost:$WEB_PORT" \
      nohup .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT" --no-access-log >>"$TMP/api.log" 2>&1 &
    echo $! > "$TMP/api.pid" )
  wait_for api_healthy 30 && say "api  : started (pid $(cat "$TMP/api.pid"))  $API_URL_LOCAL" \
    || { say "api  : failed to become healthy, see .tmp/api.log"; return 1; }
}

# ---------- web ----------
web_up() {
  local pid; pid="$(pidfile_pid web)"
  if alive "$pid" && web_healthy; then say "web  : already running (pid $pid) $WEB_URL_LOCAL"; return 0; fi
  local replaced=0
  for p in $(port_pids "$WEB_PORT"); do
    alive "$p" || continue
    if is_gridline "$p"; then
      if web_healthy; then say "web  : reusing healthy GRIDLINE web (pid $p, not managed by dev-down)"; return 0; fi
      say "web  : replacing stale GRIDLINE web on :$WEB_PORT (pid $p)"; kill_tree "$p"; replaced=1; sleep 1
    else say "web  : port $WEB_PORT is used by a non-GRIDLINE process (pid $p). Stop it or set WEB_PORT."; return 1; fi
  done
  [ "$replaced" = 1 ] && rm -rf "$ROOT/apps/web/.next"   # a stale server may have left a half-built .next
  ( cd "$ROOT/apps/web" && API_URL="$API_URL_LOCAL" NEXT_TELEMETRY_DISABLED=1 \
      nohup npx next dev -p "$WEB_PORT" -H 127.0.0.1 >>"$TMP/web.log" 2>&1 &
    echo $! > "$TMP/web.pid" )
  wait_for web_healthy 90 && say "web  : started (pid $(cat "$TMP/web.pid"))  $WEB_URL_LOCAL" \
    || { say "web  : failed to become healthy, see .tmp/web.log"; return 1; }
}

cmd_up() {
  db_up || exit 1
  api_up || exit 1
  web_up || exit 1
  say ""; say "GRIDLINE is up"; say "  web  $WEB_URL_LOCAL"; say "  api  $API_URL_LOCAL   (docs: $API_URL_LOCAL/docs)"
  say "  logs: make dev-logs   stop: make dev-down"
}

cmd_down() {
  local n pid
  for n in web api; do
    pid="$(pidfile_pid $n)"
    if alive "$pid"; then kill_tree "$pid"; say "$n: stopped (pid $pid)"; else say "$n: nothing started by dev-up"; fi
    rm -f "$TMP/$n.pid"
  done
  say "db : left running (dev-down never stops the database)"
}

cmd_status() {
  local url host port; url="$(db_url)"
  if [ -n "$url" ]; then
    host="$(echo "$url" | sed -E 's#.*@([^:/]+).*#\1#')"; port="$(echo "$url" | sed -E 's#.*:([0-9]+)/[^/]*$#\1#')"
    pg_isready -q -h "$host" -p "${port:-5432}" && say "DB   : up      $host:${port:-5432}" || say "DB   : DOWN    $host:${port:-5432}"
  else say "DB   : unknown (run make dev-up)"; fi
  for n in api web; do
    local port_var pidv listeners health="down" label
    [ $n = api ] && port_var=$API_PORT || port_var=$WEB_PORT
    pidv="$(pidfile_pid $n)"; listeners="$(port_pids "$port_var" | tr '\n' ' ')"
    if [ $n = api ]; then api_healthy && health="healthy"; else web_healthy && health="healthy"; fi
    if alive "$pidv"; then label="managed pid $pidv"; elif [ -n "$listeners" ]; then label="external"; else label="not running"; fi
    printf '%-5s: %-8s port %s  listeners[%s] %s\n' "$(echo $n | tr a-z A-Z)" "$health" "$port_var" "${listeners% }" "($label)"
  done
  say "logs : $TMP/api.log  $TMP/web.log"
}

cmd_logs() { touch "$TMP/api.log" "$TMP/web.log"; tail -n 20 -F "$TMP/api.log" "$TMP/web.log"; }

case "${1:-}" in
  up) cmd_up;; down) cmd_down;; status) cmd_status;; logs) cmd_logs;;
  *) say "usage: $0 up|down|status|logs"; exit 2;;
esac
