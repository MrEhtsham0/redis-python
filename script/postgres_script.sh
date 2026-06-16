#!/usr/bin/env bash
#
# Bootstrap local Postgres for development.
#
# Usage (from repo root):
#   ./script/postgres_script.sh
#   make db
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${ENV_FILE:-.env}"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ENV_FILE"
  set +a
fi

# After sourcing .env, verify required vars are set
CONTAINER_NAME="postgres"
DB_NAME="${DB_NAME:?ERROR: DB_NAME not set in $ENV_FILE}"
DB_USER="${DB_USER:?ERROR: DB_USER not set in $ENV_FILE}"
DB_PASSWORD="${DB_PASSWORD:?ERROR: DB_PASSWORD not set in $ENV_FILE}"
DB_HOST="${DB_HOST:?ERROR: DB_HOST not set in $ENV_FILE}"
DB_PORT="${DB_PORT:?ERROR: DB_PORT not set in $ENV_FILE}"

access_psql() {
  docker exec -e PGPASSWORD="$DB_PASSWORD" "$CONTAINER_NAME" \
    psql -U "$DB_USER" -v ON_ERROR_STOP=1 "$@"
}

echo "==> Starting Postgres (docker compose) …"
docker compose up -d postgres --wait

echo "==> Waiting for Postgres to accept connections …"
for _ in $(seq 1 30); do
  if docker exec "$CONTAINER_NAME" pg_isready -U "$DB_USER" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! docker exec "$CONTAINER_NAME" pg_isready -U "$DB_USER" >/dev/null 2>&1; then
  echo "ERROR: Postgres is not ready. Check: docker compose logs postgres"
  exit 1
fi


echo "==> Ensuring database '$DB_NAME' exists …"
if access_psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" | grep -q 1; then
    echo "    Already exists."
else
    access_psql -d postgres -c "CREATE DATABASE \"$DB_NAME\";"
    echo "    Created."
fi

echo ""
echo "Postgres is ready."
echo "  host:     $DB_HOST"
echo "  port:     $DB_PORT"
echo "  database: $DB_NAME"
echo "  user:     $DB_USER"
