#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: sudo bash scripts/import-full-snapshot.sh <snapshot-dir>"
  exit 1
fi

SNAPSHOT_DIR="${1}"
if [[ ! -d "${SNAPSHOT_DIR}" ]]; then
  echo "Snapshot directory not found: ${SNAPSHOT_DIR}"
  exit 1
fi

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}"

PROJECT_NAME="${COMPOSE_PROJECT_NAME:-signalkiosk}"
DB_VOLUME="${PROJECT_NAME}_db_data"
UPLOADS_VOLUME="${PROJECT_NAME}_uploads_data"
CONFIG_VOLUME="${PROJECT_NAME}_config_data"

for file in db_data.tgz uploads_data.tgz config_data.tgz; do
  if [[ ! -f "${SNAPSHOT_DIR}/${file}" ]]; then
    echo "Missing snapshot file: ${SNAPSHOT_DIR}/${file}"
    exit 1
  fi
done

echo "WARNING: This will overwrite current database/uploads/config volumes."
read -r -p "Continue? (yes/no): " ANSWER
if [[ "${ANSWER}" != "yes" ]]; then
  echo "Restore cancelled."
  exit 0
fi

echo "[1/6] Stopping services"
docker compose down

echo "[2/6] Ensuring target volumes exist"
docker volume create "${DB_VOLUME}" >/dev/null
docker volume create "${UPLOADS_VOLUME}" >/dev/null
docker volume create "${CONFIG_VOLUME}" >/dev/null

echo "[3/6] Restoring database volume"
docker run --rm -v "${DB_VOLUME}:/to" -v "${SNAPSHOT_DIR}:/from" alpine sh -c "rm -rf /to/* /to/.[!.]* /to/..?* 2>/dev/null || true; cd /to && tar xzf /from/db_data.tgz"

echo "[4/6] Restoring uploads volume"
docker run --rm -v "${UPLOADS_VOLUME}:/to" -v "${SNAPSHOT_DIR}:/from" alpine sh -c "rm -rf /to/* /to/.[!.]* /to/..?* 2>/dev/null || true; cd /to && tar xzf /from/uploads_data.tgz"

echo "[5/6] Restoring config volume"
docker run --rm -v "${CONFIG_VOLUME}:/to" -v "${SNAPSHOT_DIR}:/from" alpine sh -c "rm -rf /to/* /to/.[!.]* /to/..?* 2>/dev/null || true; cd /to && tar xzf /from/config_data.tgz"

echo "[6/6] Starting services"
docker compose up -d --build app frontend

echo "Restore completed from: ${SNAPSHOT_DIR}"
