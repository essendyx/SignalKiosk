#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_SCRIPT="${SCRIPT_DIR}/setup-ubuntu-kiosk.sh"

if [[ ! -f "${TARGET_SCRIPT}" ]]; then
  echo "Fehler: ${TARGET_SCRIPT} nicht gefunden"
  exit 1
fi

echo "Hinweis: scripts/install.sh delegiert jetzt auf scripts/setup-ubuntu-kiosk.sh"
exec bash "${TARGET_SCRIPT}"
