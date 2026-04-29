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
- WebUI system controls to restart runner/backend/frontend from Settings
- Containerized runtime with Docker Compose
- FastAPI backend, Vue 3 + TypeScript frontend

## Architecture

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

If you want one single, repeatable setup path (fresh Ubuntu/Debian/Raspberry Pi OS + kiosk + autologin + fullscreen playback), follow only this section.
You can ignore the other install sections.

### 1) Run the interactive installer (recommended)

```bash
sudo apt update && sudo apt -y upgrade
sudo apt -y install git
cd ~
git clone https://github.com/essendyx/SignalKiosk.git SignalKiosk-src
cd SignalKiosk-src
sudo bash scripts/install-interactive.sh
```

The installer guides you through:

- kiosk Linux username
- release tag selection (list of available tags)
- admin and playback ports
- timezone and default admin credentials
- automatic generation of `SECRET_ENCRYPTION_KEY`, `HOST_CONTROL_TOKEN`, and `APP_SECRET_KEY`

### 2) Reboot and verify

The interactive installer already configures all of the following automatically:

- desktop packages + LightDM autologin
- kiosk hardening (no blank screen)
- auto-suspend/power-off disable
- runner user/systemd overrides for the selected kiosk user

After installation, reboot and run the generated verify script:

```bash
sudo reboot
sudo bash /opt/SignalKiosk/scripts/post-reboot-verify.sh
```

Open the Admin UI using one of the URLs printed by the installer at the end (for example `http://<device-ip>:8080`, or your configured `ADMIN_PORT`).

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


## Security Notes

- Change the default admin password immediately after first login
- Keep `.env` and database backups private
- Restrict network exposure of `ADMIN_PORT` where possible

## License

Licensed under Apache-2.0. See `LICENSE`.
