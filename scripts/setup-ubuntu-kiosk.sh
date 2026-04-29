#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Please run as root: sudo bash scripts/setup-ubuntu-kiosk.sh"
  exit 1
fi

PROJECT_DIR="/opt/SignalKiosk"
SERVICE_FILE="/etc/systemd/system/signalkiosk-cdp-runner.service"
PROFILE_DIR="/var/lib/signalkiosk/chrome-profile"

echo "[1/8] Installing host dependencies"
apt-get update
apt-get install -y ca-certificates curl gnupg lsb-release python3 python3-pip chromium-browser

if ! command -v docker >/dev/null 2>&1; then
  echo "[2/8] Installing Docker Engine + Compose plugin"
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
else
  echo "[2/8] Docker already installed"
fi

echo "[3/8] Copying project to ${PROJECT_DIR}"
mkdir -p "${PROJECT_DIR}"
cp -a . "${PROJECT_DIR}"
cd "${PROJECT_DIR}"

echo "[4/8] Preparing environment"
if [[ ! -f .env ]]; then
  cp .env.example .env
fi

PLAYBACK_PORT="$(grep '^PLAYBACK_PORT=' .env | cut -d '=' -f2 || true)"
if [[ -z "${PLAYBACK_PORT}" ]]; then
  PLAYBACK_PORT="8090"
  echo "PLAYBACK_PORT=${PLAYBACK_PORT}" >> .env
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
Environment=CHROME_BIN=/usr/bin/chromium-browser
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

echo "[8/8] Done"
echo "Admin UI: http://<server-ip>:${PLAYBACK_PORT}"
echo "Service status: systemctl status signalkiosk-cdp-runner.service"
echo "Runner logs: journalctl -u signalkiosk-cdp-runner.service -f"
