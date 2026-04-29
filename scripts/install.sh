#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_SCRIPT="${SCRIPT_DIR}/setup-ubuntu-kiosk.sh"

if [[ ! -f "${TARGET_SCRIPT}" ]]; then
  echo "Error: ${TARGET_SCRIPT} not found"
  exit 1
fi

echo "Info: scripts/install.sh now delegates to scripts/setup-ubuntu-kiosk.sh"
exec bash "${TARGET_SCRIPT}"
