# SignalKiosk

![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-0b3d91.svg)
![Docker Compose](https://img.shields.io/badge/Runtime-Docker%20Compose-1d63ed.svg)
![Backend: FastAPI](https://img.shields.io/badge/Backend-FastAPI-0f766e.svg)
![Frontend: Vue%203](https://img.shields.io/badge/Frontend-Vue%203-2f855a.svg)
![Language: TypeScript](https://img.shields.io/badge/Language-TypeScript-1f4fa3.svg)

SignalKiosk is a self-hosted kiosk and digital-signage platform for Linux.
It provides a web-based admin interface for content and scheduling, plus local fullscreen playback in Chromium for reliable single-screen operation.

## Table of Contents

- [Key Capabilities](#key-capabilities)
- [Architecture](#architecture)
- [Quick Start (Ubuntu 22.04/24.04)](#quick-start-ubuntu-22042404)
- [Configuration](#configuration)
- [Operations](#operations)
- [Backup and Restore](#backup-and-restore)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Security Notes](#security-notes)
- [License](#license)

## Key Capabilities

- Local-first kiosk operation with server and playback on the same machine
- Web admin UI for managing playback and system behavior
- Fullscreen Chromium kiosk mode via `systemd` service
- Containerized runtime with Docker Compose
- FastAPI backend, Vue 3 + TypeScript frontend

## Architecture

- `backend/`: FastAPI application, scheduling/playback logic, SQLAlchemy, Alembic, tests
- `frontend/`: Vue 3 + TypeScript admin application (Vite)
- `kiosk/`: Optional container kiosk runtime (Compose profile: `kiosk-container`)
- `scripts/`: Installation and operational helper scripts

Default production mode is host-based kiosk startup via `signalkiosk-kiosk.service`.

## Quick Start (Ubuntu 22.04/24.04)

### 1) Prepare host

```bash
sudo apt update && sudo apt -y upgrade
sudo apt -y install git
```

### 2) Clone repository

```bash
git clone https://github.com/essendyx/SignalKiosk.git
cd SignalKiosk
```

### 3) Run installer

```bash
sudo bash scripts/install.sh
```

The installer automatically:

- Installs Docker Engine and Docker Compose plugin (if missing)
- Installs project to `/opt/SignalKiosk`
- Creates `.env` from `.env.example`
- Starts services with `docker compose up -d --build`
- Creates and enables `signalkiosk-kiosk.service`
- Starts Chromium in fullscreen kiosk mode on `http://127.0.0.1:<ADMIN_PORT>/playback`

### 4) Validate installation

```bash
docker ps
docker compose -f /opt/SignalKiosk/docker-compose.yml ps
systemctl status signalkiosk-kiosk.service
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
| `ADMIN_PORT` | Admin and playback web port | `8080` |
| `DATABASE_URL` | SQLite database location | `sqlite:////data/localkiosk.db` |
| `SECRET_ENCRYPTION_KEY` | Secret key (auto-generated if empty) | `` |
| `KIOSK_MODE` | Kiosk runtime mode | `host` |
| `KIOSK_URL` | URL opened by kiosk browser | `http://127.0.0.1:8080/playback` |
| `KIOSK_DISABLE_WEB_SECURITY` | Disable Chromium web security checks (CORS/certs, unsafe) | `false` |

Apply config changes:

```bash
cd /opt/SignalKiosk
docker compose up -d
sudo systemctl restart signalkiosk-kiosk.service
```

## Operations

Runtime logs:

```bash
cd /opt/SignalKiosk
docker compose logs -f app
docker compose logs -f frontend
sudo journalctl -u signalkiosk-kiosk.service -f
```

## Backup and Restore

### Backup

```bash
docker run --rm -v signalkiosk_db_data:/from -v $(pwd):/to alpine sh -c "cd /from && tar czf /to/signalkiosk-db-backup.tgz ."
```

### Restore

```bash
docker compose down
docker run --rm -v signalkiosk_db_data:/to -v $(pwd):/from alpine sh -c "cd /to && tar xzf /from/signalkiosk-db-backup.tgz"
docker compose up -d
```

## Troubleshooting

- Black screen on local display: run `xhost +local:` on host and restart kiosk service
- API unreachable: inspect backend logs via `docker compose logs -f app`
- Kiosk not launching: inspect `journalctl -u signalkiosk-kiosk.service -n 200`
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

## Security Notes

- Change the default admin password immediately after first login
- Keep `.env` and database backups private
- Restrict network exposure of `ADMIN_PORT` where possible

## License

Licensed under Apache-2.0. See `LICENSE`.
