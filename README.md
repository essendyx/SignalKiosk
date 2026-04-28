# signalKiosk

signalKiosk ist eine lokal betreibbare Kiosk- und Digital-Signage-Software fuer Linux.
Der Server hostet Administration und Playback. Die Anzeige laeuft lokal im Chromium-Vollbild.

## Frische Linux-Installation (Ubuntu 22.04/24.04)

### 1) Server vorbereiten

```bash
sudo apt update && sudo apt -y upgrade
sudo apt -y install git
```

### 2) Repository holen

```bash
git clone <DEIN-REPO-URL> signalKiosk
cd signalKiosk
```

### 3) Installer ausfuehren

```bash
sudo bash scripts/install.sh
```

Der Installer erledigt automatisch:
- Docker Engine + Docker Compose Plugin (falls nicht vorhanden)
- Projektinstallation nach `/opt/signalKiosk`
- `.env` aus `.env.example`
- `docker compose up -d --build`
- systemd-Dienst `signalkiosk-kiosk.service`
- Chromium im echten Kiosk-Vollbild auf `http://127.0.0.1:<ADMIN_PORT>/playback`

### 4) Nach dem Install pruefen

```bash
docker ps
docker compose -f /opt/signalKiosk/docker-compose.yml ps
systemctl status signalkiosk-kiosk.service
```

Admin UI im Netzwerk:
- `http://<SERVER-IP>:8080` (oder dein `ADMIN_PORT`)

Standard-Login:
- Benutzer: `admin`
- Passwort: `admin123!`

Direkt nach Erstlogin aendern.

## Konfiguration

Datei: `/opt/signalKiosk/.env`

Wichtige Variablen:
- `ADMIN_PORT=8080`
- `DATABASE_URL=sqlite:////data/localkiosk.db`
- `SECRET_ENCRYPTION_KEY=` (leer = auto-generiert und persistent gespeichert)
- `KIOSK_MODE=host`
- `KIOSK_URL=http://127.0.0.1:8080/playback`

Nach Aenderungen:

```bash
cd /opt/signalKiosk
docker compose up -d
sudo systemctl restart signalkiosk-kiosk.service
```

## Betrieb

```bash
cd /opt/signalKiosk
docker compose logs -f app
docker compose logs -f frontend
sudo journalctl -u signalkiosk-kiosk.service -f
```

## Backup und Restore

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

- Schwarzer Bildschirm: lokal `xhost +local:` ausfuehren und Dienst neu starten.
- API nicht erreichbar: `docker compose logs -f app` pruefen.
- Kiosk startet nicht: `journalctl -u signalkiosk-kiosk.service -n 200`.
- Port belegt: `ADMIN_PORT` in `.env` aendern und neu starten.

## Entwicklung

```bash
docker compose up -d --build
docker compose run --rm app pytest -q
```

## Architektur (kurz)

- `backend/`: FastAPI, Scheduler, Playback Engine, Webhook Engine, SQLAlchemy, Alembic
- `frontend/`: Vue 3 + TypeScript Admin-Oberflaeche
- `kiosk/`: optionaler Container-Kiosk (Compose-Profil `kiosk-container`)

Default ist Host-Kiosk per systemd (produktionsnah fuer Single-Screen Linux).
