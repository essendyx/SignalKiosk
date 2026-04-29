# SignalKiosk

![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-0b3d91.svg)
![Docker Compose](https://img.shields.io/badge/Runtime-Docker%20Compose-1d63ed.svg)
![Backend: FastAPI](https://img.shields.io/badge/Backend-FastAPI-0f766e.svg)
![Frontend: Vue%203](https://img.shields.io/badge/Frontend-Vue%203-2f855a.svg)
![Language: TypeScript](https://img.shields.io/badge/Language-TypeScript-1f4fa3.svg)

SignalKiosk is a self-hosted kiosk and digital-signage platform for Linux.
It provides a web-based admin interface for content and scheduling, plus local Chromium playback controlled via Chrome DevTools Protocol (CDP).

## Table of Contents

- [Recommended One-Path Install](#recommended-one-path-install)
- [Key Capabilities](#key-capabilities)
- [Architecture](#architecture)
- [Configuration](#configuration)
- [Operations](#operations)
- [Uninstall](#uninstall)
- [Backup and Restore](#backup-and-restore)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Releases](#releases)
- [Local CDP Runner (Windows)](#local-cdp-runner-windows)
- [Security Notes](#security-notes)
- [License](#license)

## Key Capabilities

- Local-first kiosk operation with server and playback on the same machine
- Web admin UI for managing playback and system behavior
- Dedicated CDP runner service that launches and controls Chromium
- Playback is driven by structured commands (`/api/playback/command`), no iframe playback page
- WebUI system controls to restart runner/backend/frontend from Settings
- Containerized runtime with Docker Compose
- FastAPI backend, Vue 3 + TypeScript frontend

## Architecture

- `backend/`: FastAPI application, scheduling/playback logic, SQLAlchemy, Alembic, tests
- `backend/`: FastAPI application, scheduling/playback logic, command API for CDP runner
- `frontend/`: Vue 3 + TypeScript admin application (Vite)
- `cdp_runner/`: Dedicated CDP runner service (Compose profile: `cdp-runner`)
- `scripts/`: Installation and operational helper scripts

### Playback flow (CDP)

1. Backend resolves active content (default/schedule/webhook override).
2. Backend exposes the current playback command via `GET /api/playback/command`.
3. CDP runner polls the command endpoint and only navigates when command hash/revision changes.
4. Runner controls local Chrome via CDP (`Page.navigate`) in kiosk/fullscreen mode.

### Host control flow

1. A host-local control agent (`scripts/host-control-agent.py`) runs as `systemd` service.
2. Backend calls this agent on `HOST_CONTROL_URL` with `HOST_CONTROL_TOKEN`.
3. Settings page can trigger: runner restart, backend restart, frontend restart, or app+frontend restart.

## Recommended One-Path Install

If you want one single, repeatable setup path (fresh Ubuntu + kiosk + autologin + fullscreen playback), follow only this section.
You can ignore the other install sections.

### 1) Create kiosk user

```bash
sudo adduser signalkiosk
sudo usermod -aG sudo signalkiosk
su - signalkiosk
```

### 2) Install and run SignalKiosk setup

```bash
sudo apt update && sudo apt -y upgrade
sudo apt -y install git
cd ~
git clone https://github.com/essendyx/SignalKiosk.git SignalKiosk-src
cd SignalKiosk-src
sudo bash scripts/setup-ubuntu-kiosk.sh
```

### 3) Edit active config

Generate a valid Fernet key for `SECRET_ENCRYPTION_KEY`:

```bash
python3 - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
```

Copy the output and set it in `/opt/SignalKiosk/.env` as `SECRET_ENCRYPTION_KEY=<generated-key>`.

```bash
sudo nano /opt/SignalKiosk/.env
cd /opt/SignalKiosk
sudo docker compose up -d
sudo systemctl restart signalkiosk-cdp-runner.service signalkiosk-host-control.service
```

### 4) Install desktop and enable autologin

```bash
sudo apt update
sudo apt -y install xfce4 xfce4-goodies lightdm
sudo systemctl set-default graphical.target
sudo systemctl enable lightdm
sudo mkdir -p /etc/lightdm/lightdm.conf.d
sudo bash -c 'cat >/etc/lightdm/lightdm.conf.d/50-signalkiosk-autologin.conf <<EOF
[Seat:*]
autologin-user=signalkiosk
autologin-user-timeout=0
user-session=xfce
EOF'
```

### 5) Kiosk hardening (no blank screen)

```bash
sudo tee /etc/xdg/autostart/signalkiosk-display-power.desktop >/dev/null <<'EOF'
[Desktop Entry]
Type=Application
Name=SignalKiosk Display Power
Exec=sh -c "xset s off -dpms s noblank"
X-GNOME-Autostart-enabled=true
NoDisplay=true
EOF
```

### 6) Reboot and verify

```bash
sudo reboot
```

After reboot:

```bash
echo $DISPLAY
systemctl is-active signalkiosk-cdp-runner.service
journalctl -u signalkiosk-cdp-runner.service -n 50 --no-pager
```

Open admin UI: `http://<server-ip>:8080` (or your `ADMIN_PORT`).
Do not use a fixed `/playback` URL for kiosk output; the runner navigates dynamically from `GET /api/playback/command`.

### 7) Ensure runner uses logged-in desktop user (important)

Set the runner service to the kiosk user and the correct runtime dir:

```bash
id -u signalkiosk
sudo systemctl edit signalkiosk-cdp-runner.service
```

Insert:

```ini
[Service]
User=signalkiosk
Group=signalkiosk
Environment=DISPLAY=:0
Environment=XDG_RUNTIME_DIR=/run/user/1000
Environment=XAUTHORITY=/home/signalkiosk/.Xauthority
ExecStart=
ExecStart=/usr/bin/python3 /opt/SignalKiosk/cdp_runner/runner.py
```

Replace `1000` with the UID from `id -u signalkiosk` if different. Then apply:

```bash
sudo systemctl daemon-reload
sudo systemctl restart signalkiosk-cdp-runner.service
```

Fix Chrome profile permissions for that user:

```bash
sudo mkdir -p /var/lib/signalkiosk/chrome-profile
sudo chown -R signalkiosk:signalkiosk /var/lib/signalkiosk
sudo chmod -R u+rwX /var/lib/signalkiosk
sudo systemctl restart signalkiosk-cdp-runner.service
```

### 8) Disable auto-suspend, power-off, and logout behavior

On kiosk systems, disable sleep/suspend at OS and desktop level.

```bash
sudo mkdir -p /etc/systemd/logind.conf.d
sudo tee /etc/systemd/logind.conf.d/50-signalkiosk.conf >/dev/null <<'EOF'
[Login]
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
IdleAction=ignore
IdleActionSec=0
EOF
sudo systemctl restart systemd-logind
```

```bash
sudo mkdir -p /etc/systemd/sleep.conf.d
sudo tee /etc/systemd/sleep.conf.d/50-signalkiosk.conf >/dev/null <<'EOF'
[Sleep]
AllowSuspend=no
AllowHibernation=no
AllowHybridSleep=no
AllowSuspendThenHibernate=no
EOF
```

```bash
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

```bash
xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/power-button-action -n -t int -s 0
xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/sleep-button-action -n -t int -s 0
xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/hibernate-button-action -n -t int -s 0
xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/inactivity-on-ac -n -t int -s 14
xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/dpms-enabled -n -t bool -s false
```

Disable screen locker packages/services if present:

```bash
sudo systemctl disable --now light-locker 2>/dev/null || true
sudo apt -y purge light-locker xscreensaver* || true
```

Create a per-login autostart guard so XFCE cannot re-enable sleep/DPMS after updates:

```bash
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/signalkiosk-nosleep.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=SignalKiosk NoSleep
Exec=sh -c "xset s off -dpms s noblank; xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/dpms-enabled -n -t bool -s false; xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/blank-on-ac -n -t int -s 0; xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/inactivity-on-ac -n -t int -s 14"
X-GNOME-Autostart-enabled=true
EOF
```

Reboot after applying:

```bash
sudo reboot
```

Verify sleep targets are masked:

```bash
systemctl status sleep.target suspend.target hibernate.target hybrid-sleep.target --no-pager
```

Verify DPMS/screensaver state:

```bash
xset q | grep -E "DPMS is|timeout:"
```

Run the `xset` check in a local GUI terminal on the TV/monitor session.
If you run it via SSH, use:

```bash
DISPLAY=:0 xset q | grep -E "DPMS is|timeout:"
```

Expected result in GUI session:

- `DPMS is Disabled`
- `DISPLAY` usually `:0` or `:0.0`

## Configuration

Primary config file: `/opt/SignalKiosk/.env`

Minimal `.env` for this setup:

```dotenv
APP_ENV=production
APP_SECRET_KEY=change-me-to-a-long-random-secret
SECRET_ENCRYPTION_KEY=<generated-fernet-key>
ADMIN_PORT=8080
PLAYBACK_PORT=8081
DATABASE_URL=sqlite:////data/localkiosk.db
TZ=Europe/Berlin
HOST_CONTROL_URL=http://127.0.0.1:9510
HOST_CONTROL_TOKEN=change-me-to-a-long-random-token
DEFAULT_ADMIN_USERNAME=admin
DEFAULT_ADMIN_PASSWORD=admin
```

Apply config changes:

```bash
cd /opt/SignalKiosk
sudo docker compose up -d
sudo systemctl restart signalkiosk-cdp-runner.service signalkiosk-host-control.service
```

If `SECRET_ENCRYPTION_KEY` is invalid, backend startup fails with: `Fernet key must be 32 url-safe base64-encoded bytes`.

Service operations:

```bash
sudo systemctl status signalkiosk-cdp-runner.service
sudo systemctl restart signalkiosk-cdp-runner.service
sudo journalctl -u signalkiosk-cdp-runner.service -f
sudo systemctl status signalkiosk-host-control.service
sudo journalctl -u signalkiosk-host-control.service -f
```

## Operations

Runtime logs:

```bash
cd /opt/SignalKiosk
docker compose logs -f app
docker compose logs -f frontend
docker compose --profile cdp-runner logs -f cdp-runner
```

## Uninstall

Run from any directory:

```bash
sudo bash /opt/SignalKiosk/scripts/uninstall.sh
```

Options:

- Keep Docker and keep data (default): `sudo bash /opt/SignalKiosk/scripts/uninstall.sh`
- Remove app data volumes too: `sudo bash /opt/SignalKiosk/scripts/uninstall.sh --remove-data`
- Remove data + purge Docker packages: `sudo bash /opt/SignalKiosk/scripts/uninstall.sh --remove-data --purge-docker`

The uninstall script removes:

- `signalkiosk-cdp-runner.service` and `signalkiosk-host-control.service`
- `/opt/SignalKiosk` project files
- Host runner profile at `/var/lib/signalkiosk/chrome-profile`

By default, Docker volumes are kept unless `--remove-data` is used.

## Backup and Restore

### Backup

```bash
docker run --rm -v signalkiosk_db_data:/from -v $(pwd):/to alpine sh -c "cd /from && tar czf /to/signalkiosk-db-backup.tgz ."
```

### Full snapshot (recommended for image/video content)

This exports database + uploads + config volumes, so `asset_path` references remain valid after restore.

```bash
bash scripts/export-full-snapshot.sh
```

Optional output directory:

```bash
bash scripts/export-full-snapshot.sh /opt/signal-backups/snapshot-20260429
```

### Restore

```bash
docker compose down
docker run --rm -v signalkiosk_db_data:/to -v $(pwd):/from alpine sh -c "cd /to && tar xzf /from/signalkiosk-db-backup.tgz"
docker compose up -d
```

### Full snapshot restore

```bash
sudo bash scripts/import-full-snapshot.sh /opt/signal-backups/snapshot-20260429
```

## Troubleshooting

- Browser does not update: inspect `cdp-runner` logs and verify `app` is reachable
- TV shows only text console/no browser: install desktop + display manager, enable autologin, and boot into `graphical.target`
- System logs out or powers down after idle: apply step `8) Disable auto-suspend, power-off, and logout behavior`
- Screen turns black after idle: repeat step `5) Kiosk hardening (no blank screen)` from `Recommended One-Path Install`
- Manual browser test opens UI but not kiosk content: this is expected; `:8080` is admin UI and runner navigates dynamically from `GET /api/playback/command`
- Browser shows `{"detail":"Not Found"}` on `/playback` via `:8081`: expected, because `:8081` is backend API only
- `cdp-runner` logs show `Permission denied ... /var/lib/signalkiosk/chrome-profile/First Run`: fix owner/permissions with the commands in step `7`
- `cdp-runner` logs show repeated `CDP page target not available`: usually no active GUI session or service running as wrong user; apply step `7` and verify autologin/desktop session
- System still enters sleep: run `journalctl -b --no-pager | grep -Ei "suspend|hibernate|sleep|logind|power"` to identify what triggered it
- Restart buttons in Settings are disabled/failing: verify `HOST_CONTROL_TOKEN` in `.env` and host service `signalkiosk-host-control.service`
- Browser stays on `about:blank`: check `http://127.0.0.1:8081/api/playback/command` returns `changed: true` on first call and valid `content_type`
- Too many refreshes/navigations: inspect runner logs with timestamp; command updates now use revision + hash to avoid timer-only reloads
- API unreachable: inspect backend logs via `docker compose logs -f app`
- Port conflict: update `ADMIN_PORT` in `.env` and restart services

## Development

Start stack:

```bash
docker compose up -d --build
```

Run backend tests:

```bash
docker compose run --rm app pytest -q
```

Frontend local workflow:

```bash
cd frontend
npm install
npm run dev
```

## Releases

This repository publishes a GitHub release automatically when you push a tag that starts with `v`.

Example first release:

```bash
git checkout main
git pull
git tag v0.1.0
git push origin v0.1.0
```

What happens automatically after the tag push:

- GitHub Actions runs frontend install + build
- GitHub Actions runs backend tests (`pytest`)
- GitHub creates a Release with auto-generated notes
- The frontend build artifact is attached as `frontend-dist.zip`

Versioning format:

- `v0.1.0` for first usable preview
- `v1.0.0` for first stable public release
- Patch fixes use `v1.0.1`, `v1.0.2`, ...

## Local CDP Runner (Windows)

For local development with a visible browser on your Windows machine, use the provided PowerShell scripts.

Start local stack + local CDP runner:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-local-cdp.ps1
```

Unified wrapper script (recommended):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\local-cdp.ps1 start
```

All-in-one local dev wrapper (Docker + local CDP + local host-control):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\local-dev.ps1 up
powershell -ExecutionPolicy Bypass -File .\scripts\local-dev.ps1 down
```

Restart/stop via wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\local-cdp.ps1 restart
powershell -ExecutionPolicy Bypass -File .\scripts\local-cdp.ps1 stop
```

Optional parameters:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-local-cdp.ps1 -AppBaseUrl "http://127.0.0.1:8081" -ChromeBin "C:\Program Files\Google\Chrome\Application\chrome.exe" -CdpPort "9222" -PollIntervalSeconds "1.5"
```

Optional: set a dedicated browser profile path so stop can target only runner-owned Chrome:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\local-cdp.ps1 start -ChromeUserDataDir "$env:LOCALAPPDATA\SignalKiosk\cdp-chrome-profile"
```

Stop local CDP runner and controlled browser:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop-local-cdp.ps1
```

Wrapper equivalent:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\local-cdp.ps1 stop
```

Stop local CDP runner and also stop Docker services:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop-local-cdp.ps1 -StopDocker
```

Wrapper equivalents:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\local-cdp.ps1 stop -StopDocker
powershell -ExecutionPolicy Bypass -File .\scripts\local-cdp.ps1 restart
```

Notes:

- `start-local-cdp.ps1` starts `app` and `frontend` via Docker Compose and runs `cdp_runner/runner.py` locally.
- In local Windows mode, `cdp-runner` container is intentionally stopped; Chrome is controlled by the host runner.
- The local runner launches Chrome/Chromium on the host using CDP (`--remote-debugging-port`) in kiosk/fullscreen mode.
- Translate prompts are suppressed by flags and runner-managed Chrome profile preferences.
- Start script stops an already running local runner before launching a new one (prevents multi-window loops).
- If your API runs on a different port than `8081`, set `-AppBaseUrl` accordingly.

### Windows: enable Settings restart buttons

The Settings restart buttons require the host control agent.

1) Set in `.env`:

```env
HOST_CONTROL_URL=http://127.0.0.1:9510
HOST_CONTROL_TOKEN=<your-random-token>
```

2) Rebuild/restart backend so it loads env:

```powershell
docker compose up -d --build app frontend
```

3) Start host control agent locally:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-local-host-control.ps1
```

4) Stop host control agent:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop-local-host-control.ps1
```

## Security Notes

- Change the default admin password immediately after first login
- Keep `.env` and database backups private
- Restrict network exposure of `ADMIN_PORT` where possible

## License

Licensed under Apache-2.0. See `LICENSE`.
