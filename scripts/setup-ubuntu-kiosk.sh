#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Please run as root: sudo bash scripts/setup-ubuntu-kiosk.sh"
  exit 1
fi

if [[ ! -f /etc/os-release ]]; then
  echo "Unsupported system: /etc/os-release not found"
  exit 1
fi

# shellcheck source=/dev/null
. /etc/os-release

is_supported_os=false
case "${ID:-}" in
  ubuntu|debian|raspbian)
    is_supported_os=true
    ;;
esac

if [[ "${is_supported_os}" != "true" ]]; then
  case "${ID_LIKE:-}" in
    *debian*)
      is_supported_os=true
      ;;
  esac
fi

if [[ "${is_supported_os}" != "true" ]]; then
  echo "Unsupported distribution: ${ID:-unknown}. Supported: Ubuntu, Debian, Raspberry Pi OS"
  exit 1
fi

PROJECT_DIR="/opt/SignalKiosk"
SERVICE_FILE="/etc/systemd/system/signalkiosk-cdp-runner.service"
CONTROL_SERVICE_FILE="/etc/systemd/system/signalkiosk-host-control.service"
PROFILE_DIR="/var/lib/signalkiosk/chrome-profile"

install_chromium() {
  if apt-get install -y chromium-browser >/dev/null 2>&1; then
    echo "/usr/bin/chromium-browser"
    return
  fi

  apt-get install -y chromium >/dev/null 2>&1 || {
    echo "Unable to install chromium-browser or chromium"
    exit 1
  }

  if command -v chromium >/dev/null 2>&1; then
    command -v chromium
    return
  fi

  if command -v chromium-browser >/dev/null 2>&1; then
    command -v chromium-browser
    return
  fi

  echo "Chromium binary not found after installation"
  exit 1
}

get_access_ips() {
  local ips=""
  if command -v hostname >/dev/null 2>&1; then
    ips="$(hostname -I 2>/dev/null | xargs || true)"
  fi

  if [[ -z "${ips}" ]] && command -v ip >/dev/null 2>&1; then
    ips="$(ip -4 -o addr show scope global | awk '{print $4}' | cut -d/ -f1 | xargs || true)"
  fi

  if [[ -z "${ips}" ]]; then
    ips="127.0.0.1"
  fi

  printf "%s" "${ips}"
}

echo "[1/8] Installing host dependencies"
apt-get update
apt-get install -y ca-certificates curl gnupg python3 python3-pip
CHROME_BIN_PATH="$(install_chromium)"

if ! command -v docker >/dev/null 2>&1; then
  echo "[2/8] Installing Docker Engine + Compose plugin"
  curl -fsSL https://get.docker.com | sh
  apt-get install -y docker-compose-plugin
else
  echo "[2/8] Docker already installed"
fi

echo "[3/8] Copying project to ${PROJECT_DIR}"
mkdir -p "${PROJECT_DIR}"
CURRENT_DIR="$(pwd -P)"
TARGET_DIR="$(cd "${PROJECT_DIR}" && pwd -P)"
if [[ "${CURRENT_DIR}" != "${TARGET_DIR}" ]]; then
  cp -a . "${PROJECT_DIR}"
  cd "${PROJECT_DIR}"
else
  echo "[3/8] Project already in ${PROJECT_DIR}, skipping copy"
fi

echo "[4/8] Preparing environment"
if [[ ! -f .env ]]; then
  cp .env.example .env
fi

PLAYBACK_PORT="$(grep '^PLAYBACK_PORT=' .env | cut -d '=' -f2 || true)"
if [[ -z "${PLAYBACK_PORT}" ]]; then
  PLAYBACK_PORT="8090"
  echo "PLAYBACK_PORT=${PLAYBACK_PORT}" >> .env
fi

HOST_CONTROL_TOKEN="$(grep '^HOST_CONTROL_TOKEN=' .env | cut -d '=' -f2 || true)"
if [[ -z "${HOST_CONTROL_TOKEN}" ]]; then
  HOST_CONTROL_TOKEN="$(python3 - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
)"
  echo "HOST_CONTROL_TOKEN=${HOST_CONTROL_TOKEN}" >> .env
fi

if ! grep -q '^HOST_CONTROL_URL=' .env; then
  echo "HOST_CONTROL_URL=http://127.0.0.1:9510" >> .env
fi

echo "[5/8] Starting Docker services (app + frontend)"
docker compose up -d --build app frontend

echo "[6/8] Installing CDP runner Python dependencies"
python3 -m pip install -r cdp_runner/requirements.txt

echo "[7/8] Creating CDP runner systemd service"
mkdir -p "${PROFILE_DIR}"

cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=SignalKiosk CDP Runner (Host Chrome via CDP)
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${PROJECT_DIR}
Environment=APP_BASE_URL=http://127.0.0.1:${PLAYBACK_PORT}
Environment=CHROME_BIN=${CHROME_BIN_PATH}
Environment=CDP_PORT=9222
Environment=POLL_INTERVAL_SECONDS=1.5
Environment=CHROME_HEADLESS=false
Environment=CHROME_USER_DATA_DIR=${PROFILE_DIR}
ExecStart=/usr/bin/python3 ${PROJECT_DIR}/cdp_runner/runner.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now signalkiosk-cdp-runner.service

echo "[7b/8] Creating host control agent service"
cat > "${CONTROL_SERVICE_FILE}" <<EOF
[Unit]
Description=SignalKiosk Host Control Agent
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${PROJECT_DIR}
Environment=PROJECT_DIR=${PROJECT_DIR}
Environment=HOST_CONTROL_BIND=127.0.0.1
Environment=HOST_CONTROL_PORT=9510
Environment=HOST_CONTROL_TOKEN=${HOST_CONTROL_TOKEN}
Environment=RUNNER_SERVICE_NAME=signalkiosk-cdp-runner.service
ExecStart=/usr/bin/python3 ${PROJECT_DIR}/scripts/host-control-agent.py
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now signalkiosk-host-control.service

echo "[8/8] Done"
ADMIN_PORT="$(grep '^ADMIN_PORT=' .env | cut -d '=' -f2 || true)"
if [[ -z "${ADMIN_PORT}" ]]; then
  ADMIN_PORT="8080"
fi
DETECTED_IPS="$(get_access_ips)"
for IP in ${DETECTED_IPS}; do
  echo "Admin UI: http://${IP}:${ADMIN_PORT}"
done
for IP in ${DETECTED_IPS}; do
  echo "Backend/API: http://${IP}:${PLAYBACK_PORT}"
done
echo "Service status: systemctl status signalkiosk-cdp-runner.service"
echo "Runner logs: journalctl -u signalkiosk-cdp-runner.service -f"
echo "Host control status: systemctl status signalkiosk-host-control.service"
