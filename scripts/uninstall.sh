#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Please run as root: sudo bash scripts/uninstall.sh"
  exit 1
fi

PROJECT_DIR="/opt/SignalKiosk"
SERVICE_FILE="/etc/systemd/system/signalkiosk-cdp-runner.service"
CONTROL_SERVICE_FILE="/etc/systemd/system/signalkiosk-host-control.service"
PROFILE_DIR="/var/lib/signalkiosk/chrome-profile"

REMOVE_DATA=false
PURGE_DOCKER=false

for arg in "$@"; do
  case "$arg" in
    --remove-data)
      REMOVE_DATA=true
      ;;
    --purge-docker)
      PURGE_DOCKER=true
      ;;
    -h|--help)
      cat <<'EOF'
Usage: sudo bash scripts/uninstall.sh [options]

Options:
  --remove-data   Remove Docker volumes (database/uploads/logs/config)
  --purge-docker  Also remove Docker Engine + Compose plugin packages
  -h, --help      Show this help

By default, app data is kept.
EOF
      exit 0
      ;;
    *)
      echo "Unknown option: $arg"
      echo "Use --help for usage."
      exit 1
      ;;
  esac
done

echo "[1/7] Stopping and disabling systemd services"
systemctl stop signalkiosk-cdp-runner.service 2>/dev/null || true
systemctl disable signalkiosk-cdp-runner.service 2>/dev/null || true
systemctl stop signalkiosk-host-control.service 2>/dev/null || true
systemctl disable signalkiosk-host-control.service 2>/dev/null || true

echo "[2/7] Removing systemd unit files"
rm -f "${SERVICE_FILE}" "${CONTROL_SERVICE_FILE}"
systemctl daemon-reload

echo "[3/7] Stopping Docker stack"
if [[ -f "${PROJECT_DIR}/docker-compose.yml" ]]; then
  docker compose -f "${PROJECT_DIR}/docker-compose.yml" down || true
fi

echo "[4/7] Removing project files"
rm -rf "${PROJECT_DIR}"

echo "[5/7] Removing runner profile"
rm -rf "${PROFILE_DIR}"

echo "[6/7] Cleaning optional data"
if [[ "${REMOVE_DATA}" == "true" ]]; then
  docker volume rm \
    signalkiosk_db_data \
    signalkiosk_uploads_data \
    signalkiosk_logs_data \
    signalkiosk_config_data \
    signalkiosk_frontend_node_modules 2>/dev/null || true
  docker network rm signalkiosk_default 2>/dev/null || true
  echo "Removed SignalKiosk Docker volumes/networks (if present)."
else
  echo "Keeping Docker volumes (use --remove-data to delete them)."
fi

echo "[7/7] Optional Docker package purge"
if [[ "${PURGE_DOCKER}" == "true" ]]; then
  apt-get remove -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin docker-ce-rootless-extras || true
  apt-get autoremove -y || true
  rm -f /etc/apt/sources.list.d/docker.list
  rm -f /etc/apt/keyrings/docker.asc
  apt-get update || true
  echo "Docker packages purged."
else
  echo "Docker packages kept (use --purge-docker to remove them)."
fi

echo "Uninstall complete."
