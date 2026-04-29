#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}"

PROJECT_NAME="${COMPOSE_PROJECT_NAME:-signalkiosk}"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
OUT_DIR="${1:-${PROJECT_DIR}/backups/snapshot-${STAMP}}"

DB_VOLUME="${PROJECT_NAME}_db_data"
UPLOADS_VOLUME="${PROJECT_NAME}_uploads_data"
CONFIG_VOLUME="${PROJECT_NAME}_config_data"

mkdir -p "${OUT_DIR}"

echo "[1/5] Validating Docker volumes"
docker volume inspect "${DB_VOLUME}" >/dev/null
docker volume inspect "${UPLOADS_VOLUME}" >/dev/null
docker volume inspect "${CONFIG_VOLUME}" >/dev/null

echo "[2/5] Exporting database volume"
docker run --rm -v "${DB_VOLUME}:/from" -v "${OUT_DIR}:/to" alpine sh -c "cd /from && tar czf /to/db_data.tgz ."

echo "[3/5] Exporting uploads volume"
docker run --rm -v "${UPLOADS_VOLUME}:/from" -v "${OUT_DIR}:/to" alpine sh -c "cd /from && tar czf /to/uploads_data.tgz ."

echo "[4/5] Exporting config volume"
docker run --rm -v "${CONFIG_VOLUME}:/from" -v "${OUT_DIR}:/to" alpine sh -c "cd /from && tar czf /to/config_data.tgz ."

echo "[5/5] Writing manifest"
if [[ -f ".env" ]]; then
  cp ".env" "${OUT_DIR}/.env.snapshot"
fi

cat > "${OUT_DIR}/manifest.json" <<EOF
{
  "version": 1,
  "created_at_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "project_name": "${PROJECT_NAME}",
  "files": [
    "db_data.tgz",
    "uploads_data.tgz",
    "config_data.tgz",
    ".env.snapshot"
  ]
}
EOF

echo "Snapshot created: ${OUT_DIR}"
