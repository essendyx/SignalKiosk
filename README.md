# SignalKiosk

![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-0b3d91.svg)
![Docker Compose](https://img.shields.io/badge/Runtime-Docker%20Compose-1d63ed.svg)
![Backend: FastAPI](https://img.shields.io/badge/Backend-FastAPI-0f766e.svg)
![Frontend: Vue%203](https://img.shields.io/badge/Frontend-Vue%203-2f855a.svg)
![Language: TypeScript](https://img.shields.io/badge/Language-TypeScript-1f4fa3.svg)

SignalKiosk is a self-hosted kiosk and digital-signage platform for Linux.
It provides a web-based admin interface for content and scheduling, plus local Chromium playback controlled via Chrome DevTools Protocol (CDP).

## Table of Contents

- [Key Capabilities](#key-capabilities)
- [Architecture](#architecture)
- [Quick Start (Ubuntu 22.04/24.04)](#quick-start-ubuntu-22042404)
- [Fresh Ubuntu End-to-End (Exact Steps)](#fresh-ubuntu-end-to-end-exact-steps)
- [Fresh Ubuntu Kiosk Setup](#fresh-ubuntu-kiosk-setup)
- [Kiosk Hardening](#kiosk-hardening)
- [Configuration](#configuration)
- [Operations](#operations)
- [Uninstall](#uninstall)
- [Backup and Restore](#backup-and-restore)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
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

## Quick Start (Ubuntu 22.04/24.04)

### 1) Prepare host

```bash
sudo apt update && sudo apt -y upgrade
sudo apt -y install git
```

### 2) Clone repository

```bash
# Recommended: clone outside /opt. The installer copies the project to /opt/SignalKiosk itself.
cd ~
git clone https://github.com/essendyx/SignalKiosk.git
cd SignalKiosk
```

If you already cloned to `/opt/SignalKiosk` and run `scripts/install.sh` from there, step `[3/8] Copying project to /opt/SignalKiosk` can fail with:

`cp: '.' and '/opt/SignalKiosk/.' are the same file`

In that case, clone again to a different source directory (for example `~/SignalKiosk`) and rerun the installer from that directory.

### 3) Run installer

```bash
sudo bash scripts/install.sh
```

`scripts/install.sh` now delegates to `scripts/setup-ubuntu-kiosk.sh`.

For full host-kiosk setup with local Chromium controlled via CDP (recommended for real fullscreen kiosk), use:

```bash
sudo bash scripts/setup-ubuntu-kiosk.sh
```

The installer automatically:

- Installs Docker Engine and Docker Compose plugin (if missing)
- Installs project to `/opt/SignalKiosk`
- Creates `.env` from `.env.example`
- Starts services with `docker compose up -d --build`
- Uses CDP-based playback command API for browser control

### 4) Validate installation

```bash
docker ps
docker compose -f /opt/SignalKiosk/docker-compose.yml ps
docker compose -f /opt/SignalKiosk/docker-compose.yml --profile cdp-runner ps
```

Admin UI:

- `http://<SERVER-IP>:8080` (or your configured `ADMIN_PORT`)

Default credentials:

- Username: `admin`
- Password: `admin123!`

## Configuration

Primary config file: `/opt/SignalKiosk/.env`

| Variable | Description | Example |
| --- | --- | --- |
| `ADMIN_PORT` | Admin UI web port | `8080` |
| `DATABASE_URL` | SQLite database location | `sqlite:////data/localkiosk.db` |
| `SECRET_ENCRYPTION_KEY` | Secret key (auto-generated if empty) | `` |
| `CDP_POLL_INTERVAL_SECONDS` | Runner polling interval for playback commands | `1.5` |
| `CDP_PORT` | Internal Chrome DevTools port used by runner | `9222` |
| `CHROME_HEADLESS` | Run browser headless in CDP runner | `false` |
| `CHROME_ALLOW_INSECURE` | Relax browser security checks (unsafe) | `false` |
| `HOST_CONTROL_URL` | Host control agent URL used by backend | `http://127.0.0.1:9510` |
| `HOST_CONTROL_TOKEN` | Shared token between backend and host control agent | `` |

For local Windows runner scripts, these parameters are relevant:

- `-AppBaseUrl` (default `http://127.0.0.1:8081`)
- `-ChromeBin` (auto-detected if omitted)
- `-CdpPort` (default `9222`)
- `-PollIntervalSeconds` (default `1.5`)
- `-ChromeUserDataDir` (default `%LOCALAPPDATA%\SignalKiosk\cdp-chrome-profile`)

Apply config changes:

```bash
cd /opt/SignalKiosk
docker compose up -d
docker compose --profile cdp-runner up -d cdp-runner
```

## Fresh Ubuntu End-to-End (Exact Steps)

Use this procedure on a blank Ubuntu 22.04/24.04 install.

### 1) Create kiosk user with sudo rights

Pick a username (example: `signalkiosk`) and create it:

```bash
sudo adduser signalkiosk
sudo usermod -aG sudo signalkiosk
```

Optional but recommended for Docker CLI without sudo after login:

```bash
sudo usermod -aG docker signalkiosk
```

Switch to this user:

```bash
su - signalkiosk
```

### 2) Base system update

```bash
sudo apt update && sudo apt -y upgrade
sudo apt -y install git
```

### 3) Clone repository (outside `/opt`)

```bash
cd ~
git clone https://github.com/essendyx/SignalKiosk.git SignalKiosk-src
cd SignalKiosk-src
```

### 4) Run kiosk installer

```bash
sudo bash scripts/setup-ubuntu-kiosk.sh
```

### 5) Configure environment

The installer copies the project to `/opt/SignalKiosk` and creates `/opt/SignalKiosk/.env`.
Edit that file (not the one in your home clone):

```bash
sudo nano /opt/SignalKiosk/.env
```

Apply changes:

```bash
cd /opt/SignalKiosk
sudo docker compose up -d
sudo systemctl restart signalkiosk-cdp-runner.service
sudo systemctl restart signalkiosk-host-control.service
```

### 6) Install desktop and enable GUI boot

```bash
sudo apt update
sudo apt -y install xfce4 xfce4-goodies lightdm
sudo systemctl set-default graphical.target
sudo systemctl enable lightdm
```

### 7) Enable automatic desktop login (required for visible playback)

```bash
sudo mkdir -p /etc/lightdm/lightdm.conf.d
sudo bash -c 'cat >/etc/lightdm/lightdm.conf.d/50-signalkiosk-autologin.conf <<EOF
[Seat:*]
autologin-user=signalkiosk
autologin-user-timeout=0
user-session=xfce
EOF'
```

If your username is not `signalkiosk`, replace `autologin-user=signalkiosk` accordingly.

### 8) Reboot and verify

```bash
sudo reboot
```

After reboot (on local terminal in the GUI session):

```bash
echo $DISPLAY
systemctl is-active signalkiosk-cdp-runner.service
systemctl is-active signalkiosk-host-control.service
journalctl -u signalkiosk-cdp-runner.service -n 80 --no-pager
```

`echo $DISPLAY` should typically be `:0` (sometimes `:1`).

## Fresh Ubuntu Kiosk Setup

Use this on a clean Ubuntu host when you want backend/frontend in Docker but kiosk Chromium on the host.

Run:

```bash
sudo bash scripts/setup-ubuntu-kiosk.sh
```

What the script does:

- Installs Docker (if missing), Python, and Chromium
- Copies project to `/opt/SignalKiosk`
- Creates `.env` from `.env.example` if needed
- Starts `app` and `frontend` via Docker Compose
- Installs `cdp_runner` Python dependencies on host
- Creates and enables `signalkiosk-cdp-runner.service`
- Creates and enables `signalkiosk-host-control.service`

### Required for visible playback on TV/monitor

Host-mode playback needs a running Linux desktop session (X11). If the machine only boots to a text console (TTY), Chromium cannot open a visible kiosk window.

Install a lightweight desktop + display manager:

```bash
sudo apt update
sudo apt -y install xfce4 xfce4-goodies lightdm
sudo systemctl set-default graphical.target
sudo systemctl enable lightdm
```

Enable automatic login for kiosk user (example: `signalkiosk`):

```bash
sudo bash -c 'cat >/etc/lightdm/lightdm.conf.d/50-signalkiosk-autologin.conf <<EOF
[Seat:*]
autologin-user=signalkiosk
autologin-user-timeout=0
user-session=xfce
EOF'
```

Then reboot:

```bash
sudo reboot
```

After reboot, verify a GUI session is active and restart the runner once:

```bash
echo $DISPLAY
sudo systemctl restart signalkiosk-cdp-runner.service
journalctl -u signalkiosk-cdp-runner.service -n 80 --no-pager
```

`echo $DISPLAY` should usually be `:0` (sometimes `:1`).

## Kiosk Hardening

Use this to prevent screen blanking, screensaver lock, and DPMS power-off on kiosk displays.

### 1) Disable X11 screensaver and DPMS for each GUI login

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

### 2) Disable XFCE session lock/saver defaults

```bash
mkdir -p ~/.config/xfce4/xfconf/xfce-perchannel-xml
cat > ~/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-screensaver.xml <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<channel name="xfce4-screensaver" version="1.0">
  <property name="lock" type="bool" value="false"/>
  <property name="idle-activation" type="bool" value="false"/>
  <property name="mode" type="int" value="0"/>
</channel>
EOF
```

### 3) Apply now

Log out and log in again (or reboot):

```bash
sudo reboot
```

Verify after GUI login:

```bash
xset q | grep -E "DPMS is|timeout:"
```

Expected indicators:

- `DPMS is Disabled`
- Screensaver timeout values show `0`

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
- Screen turns black after idle: apply steps in `Kiosk Hardening` to disable screensaver and DPMS
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
