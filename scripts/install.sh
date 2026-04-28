#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Bitte als root ausfuehren: sudo bash scripts/install.sh"
  exit 1
fi

PROJECT_DIR="/opt/SignalKiosk"
ADMIN_PORT_DEFAULT="8080"

echo "[1/8] Abhaengigkeiten installieren"
apt-get update
apt-get install -y ca-certificates curl gnupg lsb-release x11-xserver-utils chromium-browser

if ! command -v docker >/dev/null 2>&1; then
  echo "[2/8] Docker installieren"
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

echo "[3/8] Projekt nach ${PROJECT_DIR} kopieren"
mkdir -p "${PROJECT_DIR}"
cp -a . "${PROJECT_DIR}"
cd "${PROJECT_DIR}"

echo "[4/8] .env erzeugen"
if [[ ! -f .env ]]; then
  cp .env.example .env
fi
if ! grep -q '^ADMIN_PORT=' .env; then
  echo "ADMIN_PORT=${ADMIN_PORT_DEFAULT}" >> .env
fi
ADMIN_PORT="$(grep '^ADMIN_PORT=' .env | cut -d '=' -f2)"

echo "[5/8] Docker Services starten"
docker compose up -d --build

echo "[6/8] Host-Kiosk Service konfigurieren"
cat >/usr/local/bin/signalKiosk-host-kiosk <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
export DISPLAY=:0
if command -v xset >/dev/null 2>&1; then
  xset s off || true
  xset -dpms || true
  xset s noblank || true
fi
while true; do
  chromium-browser \
    --kiosk \
    --no-first-run \
    --disable-session-crashed-bubble \
    --disable-infobars \
    --autoplay-policy=no-user-gesture-required \
    "http://127.0.0.1:${ADMIN_PORT}/playback"
  sleep 2
done
EOF
sed -i "s/\${ADMIN_PORT}/${ADMIN_PORT}/g" /usr/local/bin/signalKiosk-host-kiosk
chmod +x /usr/local/bin/signalKiosk-host-kiosk

cat >/etc/systemd/system/signalkiosk-kiosk.service <<'EOF'
[Unit]
Description=SignalKiosk Host Chromium Kiosk
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/signalKiosk-host-kiosk
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable signalkiosk-kiosk.service

echo "[7/8] Hinweis X11 Zugriff"
echo "Falls Chromium kein Bild zeigt: auf dem lokalen Desktop einmal 'xhost +local:' ausfuehren."

echo "[8/8] Fertig"
echo "Admin UI: http://<server-ip>:${ADMIN_PORT}"
echo "Kiosk lokal: Chromium Fullscreen ueber systemd Dienst signalkiosk-kiosk.service"
