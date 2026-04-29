import json
import html
import os
import re
import secrets
import uuid
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta
import httpx
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from .config import settings
from .db import get_db
from .deps import get_current_user
from .models import AuditLog, AuthProfile, Content, OverrideEvent, PlaybackState, Preset, PresetItem, Schedule, SystemSetting, User
from .schemas import AuthProfileIn, AuthProfileOut, ConfigImportIn, ContentIn, ContentListOut, ContentOut, LoginIn, PresetIn, PresetItemIn, PresetItemOut, PresetOut, ScheduleIn, ScheduleOut, SystemSettingIn, SystemSettingOut, TokenOut, WebhookConfigIn, WebhookTokenIn, WebhookTriggerIn
from .security import create_access_token, decrypt_secret, encrypt_secret, hash_password, hash_token, verify_password
from .services import advance_rotation, ensure_playback_state

app = FastAPI(title="SignalKiosk", version="1.1.0")

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/data/uploads"))
MAX_UPLOAD_SIZE = 200 * 1024 * 1024
ALLOWED_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
    "video/mp4",
    "video/webm",
    "video/ogg",
}


def _mask_auth_config(raw: dict[str, str]) -> dict[str, str]:
    masked: dict[str, str] = {}
    for key, value in raw.items():
        low = key.lower()
        if any(word in low for word in ["password", "token", "secret", "key", "cookie"]):
            masked[key] = "********"
        else:
            masked[key] = value
    return masked


def _sanitize_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "-", name)
    return cleaned or "upload"


def _normalize_content_payload(payload: ContentIn) -> ContentIn:
    try:
        cfg = json.loads(payload.config_json or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="config_json muss gueltiges JSON sein") from exc

    if payload.type == "webpage":
        url = str(cfg.get("url", "")).strip()
        if not url:
            raise HTTPException(status_code=400, detail="Webseite benoetigt eine URL")
        cfg = {"url": url}
    elif payload.type == "html":
        html = str(cfg.get("html", "")).strip()
        if not html:
            raise HTTPException(status_code=400, detail="HTML-Inhalt darf nicht leer sein")
        cfg = {"html": html}
    elif payload.type in {"image", "video"}:
        url = str(cfg.get("url", "")).strip()
        asset_path = str(cfg.get("asset_path", "")).strip()
        if not url and not asset_path:
            raise HTTPException(status_code=400, detail="Bild/Video benoetigt Upload oder URL")
        normalized: dict[str, str] = {}
        if asset_path:
            normalized["asset_path"] = asset_path
        if url:
            normalized["url"] = url
        cfg = normalized
    else:
        raise HTTPException(status_code=400, detail="Unbekannter Inhaltstyp")

    payload.config_json = json.dumps(cfg)
    return payload


def _validate_preset_item_durations(db: Session, preset_id: str, candidate: PresetItemIn, exclude_item_id: str | None = None) -> None:
    existing = db.execute(select(PresetItem).where(PresetItem.preset_id == preset_id)).scalars().all()

    rows: list[tuple[bool, int | None]] = []
    for item in existing:
        if exclude_item_id and item.id == exclude_item_id:
            continue
        rows.append((item.enabled, item.duration_seconds))

    rows.append((candidate.enabled, candidate.duration_seconds))
    enabled_rows = [row for row in rows if row[0]]
    if len(enabled_rows) <= 1:
        return
    if any(duration is None for _, duration in enabled_rows):
        raise HTTPException(
            status_code=400,
            detail="Bei mehreren Inhalten im Preset muss fuer jeden aktiven Inhalt eine Dauer gesetzt sein",
        )


def _mark_playback_dirty(db: Session) -> None:
    rev = db.get(SystemSetting, "playback.revision")
    current = 0
    if rev:
        try:
            current = int(json.loads(rev.value_json).get("value", 0))
        except Exception:
            current = 0
        rev.value_json = json.dumps({"value": current + 1})
    else:
        rev = SystemSetting(key="playback.revision", value_json=json.dumps({"value": 1}))
    db.add(rev)


def _get_playback_revision(db: Session) -> int:
    rev = db.get(SystemSetting, "playback.revision")
    if not rev:
        return 0
    try:
        return int(json.loads(rev.value_json).get("value", 0))
    except Exception:
        return 0


def _get_central_webhook_config(db: Session) -> dict[str, object]:
    raw = db.get(SystemSetting, "webhook.central_config")
    if not raw:
        return {"enabled": True, "token_hash": ""}
    try:
        value = json.loads(raw.value_json)
    except Exception:
        value = {}
    if not isinstance(value, dict):
        value = {}
    tokens_raw = value.get("tokens", [])
    tokens: list[dict[str, str]] = []
    if isinstance(tokens_raw, list):
        for item in tokens_raw:
            if not isinstance(item, dict):
                continue
            token_id = str(item.get("id", "")).strip()
            token_hash_value = str(item.get("token_hash", "")).strip()
            token_encrypted = str(item.get("token_encrypted", "")).strip()
            if not token_id or not token_hash_value or not token_encrypted:
                continue
            tokens.append(
                {
                    "id": token_id,
                    "name": str(item.get("name", "Token")).strip() or "Token",
                    "token_hash": token_hash_value,
                    "token_encrypted": token_encrypted,
                }
            )
    legacy_hash = str(value.get("token_hash", "")).strip()
    return {
        "enabled": bool(value.get("enabled", True)),
        "tokens": tokens,
        "legacy_token_hash": legacy_hash,
    }


def _put_central_webhook_config(db: Session, enabled: bool, tokens: list[dict[str, str]], legacy_token_hash: str = "") -> None:
    raw = db.get(SystemSetting, "webhook.central_config")
    payload = {"enabled": enabled, "tokens": tokens, "token_hash": legacy_token_hash}
    if not raw:
        raw = SystemSetting(key="webhook.central_config", value_json=json.dumps(payload))
    else:
        raw.value_json = json.dumps(payload)
    db.add(raw)


def _normalize_webhook_trigger_payload(payload: WebhookTriggerIn) -> dict[str, object]:
    content_type = str(payload.content_type or "").strip().lower()
    apply_mode = str(payload.apply_mode or "replace_now").strip().lower()
    if content_type not in {"webpage", "html", "image", "video"}:
        raise HTTPException(status_code=400, detail="content_type muss webpage, html, image oder video sein")
    if apply_mode not in {"replace_now", "queue_next_once"}:
        raise HTTPException(status_code=400, detail="apply_mode muss replace_now oder queue_next_once sein")

    data: dict[str, object] = {
        "content_type": content_type,
        "duration_seconds": payload.duration_seconds,
        "apply_mode": apply_mode,
        "priority": payload.priority,
    }

    if content_type == "webpage":
        url = str(payload.url or "").strip()
        if not url:
            raise HTTPException(status_code=400, detail="webpage benoetigt url")
        data["url"] = url
    elif content_type == "html":
        html_snippet = str(payload.html or "").strip()
        if not html_snippet:
            raise HTTPException(status_code=400, detail="html darf nicht leer sein")
        data["html"] = html_snippet
    else:
        url = str(payload.url or "").strip()
        asset_path = str(payload.asset_path or "").strip()
        if not url and not asset_path:
            raise HTTPException(status_code=400, detail="image/video benoetigt url oder asset_path")
        if url:
            data["url"] = url
        if asset_path:
            data["asset_path"] = asset_path

    return data


def _activate_override_event_now(db: Session, event: OverrideEvent, now: datetime) -> PlaybackState:
    state = ensure_playback_state(db)
    payload = json.loads(event.payload_json)
    payload["reason"] = "central webhook override"
    state.active_mode = "override"
    state.active_preset_id = None
    state.active_override_id = event.id
    state.active_content_id = None
    state.started_at = now
    state.ends_at = event.ends_at
    state.state_json = json.dumps(payload)
    db.add(state)
    db.commit()
    db.refresh(state)
    return state


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def playback_referrer_policy(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/playback"):
        response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.on_event("startup")
def startup() -> None:
    from .db import SessionLocal
    db = SessionLocal()
    try:
        admin = db.execute(select(User).where(User.username == settings.default_admin_username)).scalars().first()
        if not admin:
            db.add(User(username=settings.default_admin_username, password_hash=hash_password(settings.default_admin_password), role="admin"))
            db.commit()
        ensure_playback_state(db)
    finally:
        db.close()


UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(UPLOAD_DIR)), name="media")


@app.post("/api/auth/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.username == payload.username)).scalars().first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return TokenOut(access_token=create_access_token(user.id, user.role))


@app.get("/api/auth/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "username": user.username, "role": user.role}


@app.get("/api/contents", response_model=ContentListOut)
def list_contents(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    search: str = Query(default=""),
    content_type: str = Query(default=""),
):
    stmt = select(Content)
    if search:
        stmt = stmt.where(Content.name.ilike(f"%{search}%"))
    if content_type:
        stmt = stmt.where(Content.type == content_type)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(stmt.order_by(Content.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).scalars().all()
    return ContentListOut(items=rows, total=total, page=page, page_size=page_size)


@app.post("/api/contents", response_model=ContentOut)
def create_content(payload: ContentIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    payload = _normalize_content_payload(payload)
    obj = Content(**payload.model_dump())
    db.add(obj)
    _mark_playback_dirty(db)
    db.add(AuditLog(actor_type="user", actor_id=user.id, action="create", entity_type="content", entity_id=obj.id, metadata_json="{}"))
    db.commit()
    db.refresh(obj)
    return obj


@app.put("/api/contents/{content_id}", response_model=ContentOut)
def update_content(content_id: str, payload: ContentIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = db.get(Content, content_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    payload = _normalize_content_payload(payload)
    for key, value in payload.model_dump().items():
        setattr(obj, key, value)
    db.add(obj)
    _mark_playback_dirty(db)
    db.add(AuditLog(actor_type="user", actor_id=user.id, action="update", entity_type="content", entity_id=obj.id, metadata_json="{}"))
    db.commit()
    db.refresh(obj)
    return obj


@app.delete("/api/contents/{content_id}")
def delete_content(content_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = db.get(Content, content_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(obj)
    _mark_playback_dirty(db)
    db.add(AuditLog(actor_type="user", actor_id=user.id, action="delete", entity_type="content", entity_id=content_id, metadata_json="{}"))
    db.commit()
    return {"status": "deleted"}


@app.post("/api/presets", response_model=PresetOut)
def create_preset(payload: PresetIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    if payload.is_default:
        db.query(Preset).update({Preset.is_default: False})
    obj = Preset(**payload.model_dump())
    db.add(obj)
    _mark_playback_dirty(db)
    db.commit()
    db.refresh(obj)
    return obj


@app.put("/api/presets/{preset_id}", response_model=PresetOut)
def update_preset(preset_id: str, payload: PresetIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    obj = db.get(Preset, preset_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    if payload.is_default:
        db.query(Preset).update({Preset.is_default: False})
    for key, value in payload.model_dump().items():
        setattr(obj, key, value)
    db.add(obj)
    _mark_playback_dirty(db)
    db.commit()
    db.refresh(obj)
    return obj


@app.delete("/api/presets/{preset_id}")
def delete_preset(preset_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    obj = db.get(Preset, preset_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(obj)
    _mark_playback_dirty(db)
    db.commit()
    return {"status": "deleted"}


@app.get("/api/presets", response_model=list[PresetOut])
def list_presets(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.execute(select(Preset).order_by(Preset.created_at.desc())).scalars().all()


@app.post("/api/presets/{preset_id}/items")
def add_preset_item(preset_id: str, payload: PresetItemIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    if not db.get(Preset, preset_id):
        raise HTTPException(status_code=404, detail="Preset not found")
    _validate_preset_item_durations(db, preset_id, payload)
    item = PresetItem(preset_id=preset_id, **payload.model_dump())
    db.add(item)
    _mark_playback_dirty(db)
    db.commit()
    db.refresh(item)
    return {"id": item.id}


@app.get("/api/presets/{preset_id}/items", response_model=list[PresetItemOut])
def list_preset_items(preset_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    if not db.get(Preset, preset_id):
        raise HTTPException(status_code=404, detail="Preset not found")
    return db.execute(select(PresetItem).where(PresetItem.preset_id == preset_id).order_by(PresetItem.position.asc())).scalars().all()


@app.delete("/api/preset-items/{item_id}")
def delete_preset_item(item_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    item = db.get(PresetItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(item)
    _mark_playback_dirty(db)
    db.commit()
    return {"status": "deleted"}


@app.put("/api/preset-items/{item_id}", response_model=PresetItemOut)
def update_preset_item(item_id: str, payload: PresetItemIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    item = db.get(PresetItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    _validate_preset_item_durations(db, item.preset_id, payload, exclude_item_id=item.id)
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.add(item)
    _mark_playback_dirty(db)
    db.commit()
    db.refresh(item)
    return item


@app.post("/api/uploads")
def upload_media(file: UploadFile = File(...), _: User = Depends(get_current_user)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Dateiname fehlt")
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail="Dateityp nicht erlaubt")

    suffix = Path(file.filename).suffix.lower()
    target_name = f"{uuid.uuid4()}-{_sanitize_filename(Path(file.filename).stem)}{suffix}"
    target = UPLOAD_DIR / target_name

    size = 0
    with target.open("wb") as out:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_UPLOAD_SIZE:
                out.close()
                target.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Datei ist zu gross")
            out.write(chunk)

    return {
        "asset_path": f"/media/{target_name}",
        "name": file.filename,
        "mime": file.content_type,
        "size": size,
    }


@app.get("/api/schedules", response_model=list[ScheduleOut])
def list_schedules(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.execute(select(Schedule).order_by(Schedule.priority.desc())).scalars().all()


@app.post("/api/schedules", response_model=ScheduleOut)
def create_schedule(payload: ScheduleIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    if not db.get(Preset, payload.preset_id):
        raise HTTPException(status_code=400, detail="Invalid preset_id")
    obj = Schedule(**payload.model_dump())
    db.add(obj)
    _mark_playback_dirty(db)
    db.commit()
    db.refresh(obj)
    return obj


@app.put("/api/schedules/{schedule_id}", response_model=ScheduleOut)
def update_schedule(schedule_id: str, payload: ScheduleIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    obj = db.get(Schedule, schedule_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    if not db.get(Preset, payload.preset_id):
        raise HTTPException(status_code=400, detail="Invalid preset_id")
    for key, value in payload.model_dump().items():
        setattr(obj, key, value)
    db.add(obj)
    _mark_playback_dirty(db)
    db.commit()
    db.refresh(obj)
    return obj


@app.delete("/api/schedules/{schedule_id}")
def delete_schedule(schedule_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    obj = db.get(Schedule, schedule_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(obj)
    _mark_playback_dirty(db)
    db.commit()
    return {"status": "deleted"}


@app.get("/api/webhook-config")
def get_webhook_config(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    cfg = _get_central_webhook_config(db)
    tokens_out: list[dict[str, str]] = []
    for item in cfg["tokens"]:
        try:
            plain = decrypt_secret(str(item["token_encrypted"]))
        except Exception:
            plain = ""
        preview = ""
        if plain:
            if len(plain) <= 10:
                preview = plain[:3] + "..."
            else:
                preview = plain[:6] + "..." + plain[-4:]
        tokens_out.append({"id": str(item["id"]), "name": str(item["name"]), "token_preview": preview})
    return {
        "endpoint": "/webhook",
        "enabled": bool(cfg["enabled"]),
        "tokens": tokens_out,
        "token_configured": bool(tokens_out) or bool(cfg["legacy_token_hash"]),
        "legacy_token_configured": bool(cfg["legacy_token_hash"]),
    }


@app.put("/api/webhook-config")
def put_webhook_config(payload: WebhookConfigIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    existing = _get_central_webhook_config(db)
    token_count = len(existing["tokens"])
    if token_count == 0 and not existing["legacy_token_hash"]:
        raise HTTPException(status_code=400, detail="Mindestens ein Token muss hinterlegt sein")
    _put_central_webhook_config(db, payload.enabled, existing["tokens"], str(existing["legacy_token_hash"]))
    db.commit()
    return {"status": "ok", "endpoint": "/webhook", "enabled": payload.enabled, "token_configured": True}


@app.post("/api/webhook-config/tokens")
def create_webhook_token(payload: WebhookTokenIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    name_clean = str(payload.name or "").strip()
    if not name_clean:
        raise HTTPException(status_code=400, detail="Token-Name darf nicht leer sein")
    token_clean = secrets.token_hex(24)
    cfg = _get_central_webhook_config(db)
    tokens = list(cfg["tokens"])
    token_hash_value = hash_token(token_clean)
    if any(str(item.get("token_hash", "")) == token_hash_value for item in tokens):
        raise HTTPException(status_code=409, detail="Token existiert bereits")
    tokens.append(
        {
            "id": str(uuid.uuid4()),
            "name": name_clean,
            "token_hash": token_hash_value,
            "token_encrypted": encrypt_secret(token_clean),
        }
    )
    _put_central_webhook_config(db, bool(cfg["enabled"]), tokens, str(cfg["legacy_token_hash"]))
    db.commit()
    return {"status": "created"}


@app.get("/api/webhook-config/tokens/{token_id}/secret")
def get_webhook_token_secret(token_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    cfg = _get_central_webhook_config(db)
    selected = next((item for item in cfg["tokens"] if str(item.get("id", "")) == token_id), None)
    if not selected:
        raise HTTPException(status_code=404, detail="Token not found")
    try:
        plain = decrypt_secret(str(selected.get("token_encrypted", "")))
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Token konnte nicht gelesen werden") from exc
    return {"id": token_id, "name": str(selected.get("name", "Token")), "token": plain}


@app.delete("/api/webhook-config/tokens/{token_id}")
def delete_webhook_token(token_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    cfg = _get_central_webhook_config(db)
    tokens = list(cfg["tokens"])
    filtered = [item for item in tokens if str(item.get("id", "")) != token_id]
    if len(filtered) == len(tokens):
        raise HTTPException(status_code=404, detail="Token not found")
    if len(filtered) == 0 and not cfg["legacy_token_hash"]:
        raise HTTPException(status_code=400, detail="Mindestens ein Token muss hinterlegt bleiben")
    _put_central_webhook_config(db, bool(cfg["enabled"]), filtered, str(cfg["legacy_token_hash"]))
    db.commit()
    return {"status": "deleted"}


@app.post("/api/auth-profiles", response_model=AuthProfileOut)
def create_auth_profile(payload: AuthProfileIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    encrypted_cfg = encrypt_secret(json.dumps(payload.config))
    obj = AuthProfile(name=payload.name, type=payload.type, encrypted_config_json=encrypted_cfg)
    db.add(obj)
    db.add(AuditLog(actor_type="user", actor_id=user.id, action="create", entity_type="auth_profile", entity_id=obj.id, metadata_json="{}"))
    db.commit()
    db.refresh(obj)
    return AuthProfileOut(
        id=obj.id,
        name=obj.name,
        type=obj.type,
        config_masked=_mask_auth_config(payload.config),
        created_at=obj.created_at,
        updated_at=obj.updated_at,
    )


@app.get("/api/auth-profiles", response_model=list[AuthProfileOut])
def list_auth_profiles(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.execute(select(AuthProfile).order_by(AuthProfile.created_at.desc())).scalars().all()
    out: list[AuthProfileOut] = []
    for row in rows:
        cfg = json.loads(decrypt_secret(row.encrypted_config_json))
        out.append(AuthProfileOut(id=row.id, name=row.name, type=row.type, config_masked=_mask_auth_config(cfg), created_at=row.created_at, updated_at=row.updated_at))
    return out


@app.put("/api/auth-profiles/{profile_id}", response_model=AuthProfileOut)
def update_auth_profile(profile_id: str, payload: AuthProfileIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = db.get(AuthProfile, profile_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    obj.name = payload.name
    obj.type = payload.type
    obj.encrypted_config_json = encrypt_secret(json.dumps(payload.config))
    db.add(obj)
    db.add(AuditLog(actor_type="user", actor_id=user.id, action="update", entity_type="auth_profile", entity_id=obj.id, metadata_json="{}"))
    db.commit()
    db.refresh(obj)
    return AuthProfileOut(
        id=obj.id,
        name=obj.name,
        type=obj.type,
        config_masked=_mask_auth_config(payload.config),
        created_at=obj.created_at,
        updated_at=obj.updated_at,
    )


@app.get("/api/system/settings", response_model=list[SystemSettingOut])
def list_settings(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.execute(select(SystemSetting).order_by(SystemSetting.key.asc())).scalars().all()
    return [SystemSettingOut(key=item.key, value=json.loads(item.value_json), updated_at=item.updated_at) for item in rows]


@app.put("/api/system/settings/{key}", response_model=SystemSettingOut)
def put_setting(key: str, payload: SystemSettingIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if key != payload.key:
        raise HTTPException(status_code=400, detail="Path key and payload key mismatch")
    obj = db.get(SystemSetting, key)
    if not obj:
        obj = SystemSetting(key=key, value_json=json.dumps(payload.value))
    else:
        obj.value_json = json.dumps(payload.value)
    db.add(obj)
    _mark_playback_dirty(db)
    db.add(AuditLog(actor_type="user", actor_id=user.id, action="update", entity_type="system_setting", entity_id=key, metadata_json="{}"))
    db.commit()
    db.refresh(obj)
    return SystemSettingOut(key=obj.key, value=json.loads(obj.value_json), updated_at=obj.updated_at)


@app.get("/api/system/config/export")
def export_system_config(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    sections: str | None = Query(default=None),
):
    allowed = {"settings", "contents", "presets", "preset_items", "schedules", "auth_profiles", "users"}
    selected = [item.strip() for item in (sections or "").split(",") if item.strip()]
    if not selected:
        selected = sorted(allowed)
    selected = [item for item in selected if item in allowed]

    out: dict[str, object] = {}
    if "settings" in selected:
        rows = db.execute(select(SystemSetting).order_by(SystemSetting.key.asc())).scalars().all()
        data: dict[str, object] = {}
        for row in rows:
            try:
                parsed = json.loads(row.value_json)
            except Exception:
                parsed = {"value": row.value_json}
            data[row.key] = parsed
        out["settings"] = data

    if "contents" in selected:
        rows = db.execute(select(Content).order_by(Content.created_at.asc())).scalars().all()
        out["contents"] = [
            {
                "id": row.id,
                "name": row.name,
                "type": row.type,
                "description": row.description,
                "enabled": row.enabled,
                "config_json": row.config_json,
                "default_duration_seconds": row.default_duration_seconds,
                "fallback_content_id": row.fallback_content_id,
            }
            for row in rows
        ]

    if "presets" in selected:
        rows = db.execute(select(Preset).order_by(Preset.created_at.asc())).scalars().all()
        out["presets"] = [
            {
                "id": row.id,
                "name": row.name,
                "description": row.description,
                "enabled": row.enabled,
                "is_default": row.is_default,
                "loop_mode": row.loop_mode,
                "shuffle": row.shuffle,
                "priority": row.priority,
            }
            for row in rows
        ]

    if "preset_items" in selected:
        rows = db.execute(select(PresetItem).order_by(PresetItem.preset_id.asc(), PresetItem.position.asc())).scalars().all()
        out["preset_items"] = [
            {
                "id": row.id,
                "preset_id": row.preset_id,
                "content_id": row.content_id,
                "position": row.position,
                "duration_seconds": row.duration_seconds,
                "play_until_end": row.play_until_end,
                "enabled": row.enabled,
                "transition": row.transition,
            }
            for row in rows
        ]

    if "schedules" in selected:
        rows = db.execute(select(Schedule).order_by(Schedule.created_at.asc())).scalars().all()
        out["schedules"] = [
            {
                "id": row.id,
                "name": row.name,
                "preset_id": row.preset_id,
                "enabled": row.enabled,
                "weekdays": row.weekdays,
                "start_time": row.start_time,
                "end_time": row.end_time,
                "start_date": row.start_date,
                "end_date": row.end_date,
                "timezone": row.timezone,
                "priority": row.priority,
            }
            for row in rows
        ]

    if "auth_profiles" in selected:
        rows = db.execute(select(AuthProfile).order_by(AuthProfile.created_at.asc())).scalars().all()
        out["auth_profiles"] = [
            {
                "id": row.id,
                "name": row.name,
                "type": row.type,
                "encrypted_config_json": row.encrypted_config_json,
            }
            for row in rows
        ]

    if "users" in selected:
        rows = db.execute(select(User).order_by(User.created_at.asc())).scalars().all()
        out["users"] = [
            {
                "id": row.id,
                "username": row.username,
                "password_hash": row.password_hash,
                "role": row.role,
                "enabled": row.enabled,
            }
            for row in rows
        ]

    return {
        "version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "selected_sections": selected,
        "sections": out,
    }


@app.post("/api/system/config/import")
def import_system_config(payload: ConfigImportIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    allowed = {"settings", "contents", "presets", "preset_items", "schedules", "auth_profiles", "users"}
    selected = payload.selected_sections or sorted(allowed)
    selected = [item for item in selected if item in allowed]
    sections = payload.sections if isinstance(payload.sections, dict) else {}
    imported = 0
    skipped = 0

    if "settings" in selected and isinstance(sections.get("settings"), dict):
        for key, value in dict(sections.get("settings") or {}).items():
            key_clean = str(key).strip()
            if not key_clean:
                continue
            existing = db.get(SystemSetting, key_clean)
            if existing and not payload.replace_existing:
                skipped += 1
                continue
            raw_value = value if isinstance(value, dict) else {"value": value}
            if existing:
                existing.value_json = json.dumps(raw_value)
                db.add(existing)
            else:
                db.add(SystemSetting(key=key_clean, value_json=json.dumps(raw_value)))
            imported += 1

    def upsert_by_id(rows: object, model_cls, apply):
        nonlocal imported, skipped
        if not isinstance(rows, list):
            return
        for item in rows:
            if not isinstance(item, dict):
                continue
            row_id = str(item.get("id", "")).strip()
            if not row_id:
                continue
            existing = db.get(model_cls, row_id)
            if existing and not payload.replace_existing:
                skipped += 1
                continue
            target = existing if existing else model_cls(id=row_id)
            apply(target, item)
            db.add(target)
            imported += 1

    if "contents" in selected:
        upsert_by_id(sections.get("contents"), Content, lambda t, i: (
            setattr(t, "name", str(i.get("name", ""))),
            setattr(t, "type", str(i.get("type", "webpage"))),
            setattr(t, "description", i.get("description")),
            setattr(t, "enabled", bool(i.get("enabled", True))),
            setattr(t, "config_json", str(i.get("config_json", "{}"))),
            setattr(t, "default_duration_seconds", int(i.get("default_duration_seconds", 15))),
            setattr(t, "fallback_content_id", i.get("fallback_content_id")),
        ))

    if "presets" in selected:
        upsert_by_id(sections.get("presets"), Preset, lambda t, i: (
            setattr(t, "name", str(i.get("name", ""))),
            setattr(t, "description", i.get("description")),
            setattr(t, "enabled", bool(i.get("enabled", True))),
            setattr(t, "is_default", bool(i.get("is_default", False))),
            setattr(t, "loop_mode", bool(i.get("loop_mode", True))),
            setattr(t, "shuffle", bool(i.get("shuffle", False))),
            setattr(t, "priority", int(i.get("priority", 0))),
        ))

    if "preset_items" in selected:
        upsert_by_id(sections.get("preset_items"), PresetItem, lambda t, i: (
            setattr(t, "preset_id", str(i.get("preset_id", ""))),
            setattr(t, "content_id", str(i.get("content_id", ""))),
            setattr(t, "position", int(i.get("position", 0))),
            setattr(t, "duration_seconds", i.get("duration_seconds")),
            setattr(t, "play_until_end", bool(i.get("play_until_end", False))),
            setattr(t, "enabled", bool(i.get("enabled", True))),
            setattr(t, "transition", i.get("transition")),
        ))

    if "schedules" in selected:
        upsert_by_id(sections.get("schedules"), Schedule, lambda t, i: (
            setattr(t, "name", str(i.get("name", ""))),
            setattr(t, "preset_id", str(i.get("preset_id", ""))),
            setattr(t, "enabled", bool(i.get("enabled", True))),
            setattr(t, "weekdays", str(i.get("weekdays", "0,1,2,3,4,5,6"))),
            setattr(t, "start_time", str(i.get("start_time", "00:00"))),
            setattr(t, "end_time", str(i.get("end_time", "23:59"))),
            setattr(t, "start_date", i.get("start_date")),
            setattr(t, "end_date", i.get("end_date")),
            setattr(t, "timezone", str(i.get("timezone", "UTC"))),
            setattr(t, "priority", int(i.get("priority", 0))),
        ))

    if "auth_profiles" in selected:
        upsert_by_id(sections.get("auth_profiles"), AuthProfile, lambda t, i: (
            setattr(t, "name", str(i.get("name", ""))),
            setattr(t, "type", str(i.get("type", ""))),
            setattr(t, "encrypted_config_json", str(i.get("encrypted_config_json", "{}"))),
        ))

    if "users" in selected:
        upsert_by_id(sections.get("users"), User, lambda t, i: (
            setattr(t, "username", str(i.get("username", ""))),
            setattr(t, "password_hash", str(i.get("password_hash", ""))),
            setattr(t, "role", str(i.get("role", "admin"))),
            setattr(t, "enabled", bool(i.get("enabled", True))),
        ))

    db.add(AuditLog(actor_type="user", actor_id=user.id, action="import", entity_type="config", entity_id="bulk", metadata_json=json.dumps({"imported": imported, "skipped": skipped, "selected_sections": selected})))
    db.commit()
    return {"status": "ok", "imported": imported, "skipped": skipped, "selected_sections": selected}


@app.post("/webhook")
def webhook(
    payload: WebhookTriggerIn,
    token: str = Query(default=""),
    x_signalkiosk_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    cfg = _get_central_webhook_config(db)
    if not cfg["enabled"]:
        raise HTTPException(status_code=403, detail="Webhook is disabled")
    token_hashes = {str(item["token_hash"]) for item in cfg["tokens"]}
    legacy_hash = str(cfg["legacy_token_hash"])
    if legacy_hash:
        token_hashes.add(legacy_hash)
    if not token_hashes:
        raise HTTPException(status_code=503, detail="Webhook token is not configured")
    auth_token = x_signalkiosk_token if x_signalkiosk_token else token
    if hash_token(auth_token) not in token_hashes:
        raise HTTPException(status_code=401, detail="Invalid token")
    normalized_payload = _normalize_webhook_trigger_payload(payload)

    now = datetime.now(timezone.utc)
    duration_seconds = int(normalized_payload.get("duration_seconds", 60))
    apply_mode = str(normalized_payload.get("apply_mode", "replace_now"))
    ends = now + timedelta(seconds=duration_seconds)
    event = OverrideEvent(
        source_webhook_id=None,
        action=str(normalized_payload.get("content_type", "webpage")),
        payload_json=json.dumps(normalized_payload),
        duration_seconds=duration_seconds,
        priority=int(normalized_payload.get("priority", 100)),
        ends_at=ends,
        status="queued" if apply_mode == "queue_next_once" else "active",
    )
    db.add(event)
    db.commit()

    if apply_mode == "replace_now":
        state = _activate_override_event_now(db, event, now)
    else:
        state = advance_rotation(db, now)
    return {"status": "accepted", "playback": {"mode": state.active_mode, "active_content_id": state.active_content_id, "ends_at": state.ends_at}}


@app.get("/api/playback/status")
def playback_status(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    state = advance_rotation(db, datetime.now(timezone.utc))
    state_data = json.loads(state.state_json or "{}")
    return {
        "mode": state.active_mode,
        "active_preset_id": state.active_preset_id,
        "active_content_id": state.active_content_id,
        "started_at": state.started_at,
        "ends_at": state.ends_at,
        "reason": state_data.get("reason", "unknown"),
    }


@app.get("/api/playback/public-status")
def playback_public_status(db: Session = Depends(get_db)):
    state = advance_rotation(db, datetime.now(timezone.utc))
    return {
        "active_content_id": state.active_content_id,
        "active_mode": state.active_mode,
        "ends_at": state.ends_at.isoformat() if state.ends_at else None,
        "revision": _get_playback_revision(db),
    }


def _resolve_playback_command(db: Session) -> dict[str, object]:
    state = advance_rotation(db, datetime.now(timezone.utc))
    revision = _get_playback_revision(db)
    base = {
        "revision": revision,
        "mode": state.active_mode,
        "active_content_id": state.active_content_id,
        "ends_at": state.ends_at.isoformat() if state.ends_at else None,
        "content_type": None,
        "url": None,
        "html": None,
        "asset_path": None,
    }

    if state.active_mode == "override":
        try:
            payload = json.loads(state.state_json or "{}")
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        content_type = str(payload.get("content_type") or payload.get("action") or "").strip().lower()
        if content_type in {"webpage", "play_url"} and payload.get("url"):
            base.update({"content_type": "webpage", "url": str(payload["url"])})
            return base
        if content_type in {"html", "play_html"}:
            base.update({"content_type": "html", "html": str(payload.get("html", ""))})
            return base
        if content_type == "image":
            src = str(payload.get("asset_path") or payload.get("url") or "")
            base.update({"content_type": "image", "asset_path": src, "url": src})
            return base
        if content_type == "video":
            src = str(payload.get("asset_path") or payload.get("url") or "")
            base.update({"content_type": "video", "asset_path": src, "url": src})
            return base

    if not state.active_content_id:
        base.update({"content_type": "html", "html": "<div style='font-family:sans-serif;background:#111;color:#fff;display:flex;align-items:center;justify-content:center;height:100vh'>Fallback: Kein aktiver Inhalt</div>"})
        return base

    content = db.get(Content, state.active_content_id)
    if not content:
        base.update({"content_type": "html", "html": "<div style='font-family:sans-serif;padding:18px'>Fehler: Inhalt nicht gefunden</div>"})
        return base

    try:
        cfg = json.loads(content.config_json)
    except Exception:
        cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}

    ctype = str(content.type or "").strip().lower()
    if ctype == "webpage":
        src = str(cfg.get("url", "about:blank"))
        base.update({"content_type": "webpage", "url": src})
    elif ctype == "image":
        src = str(cfg.get("asset_path") or cfg.get("url", ""))
        base.update({"content_type": "image", "asset_path": src, "url": src})
    elif ctype == "video":
        src = str(cfg.get("asset_path") or cfg.get("url", ""))
        base.update({"content_type": "video", "asset_path": src, "url": src})
    elif ctype == "html":
        base.update({"content_type": "html", "html": str(cfg.get("html", ""))})
    else:
        base.update({"content_type": "html", "html": f"<div style='font-family:sans-serif;color:#fff;background:#111;height:100vh;display:flex;align-items:center;justify-content:center;padding:18px'>Unbekannter Inhaltstyp: {html.escape(str(content.type))}</div>"})
    return base


def _playback_command_hash(command: dict[str, object]) -> str:
    fingerprint = {
        "mode": command.get("mode"),
        "active_content_id": command.get("active_content_id"),
        "content_type": command.get("content_type"),
        "url": command.get("url"),
        "html": command.get("html"),
        "asset_path": command.get("asset_path"),
    }
    raw = json.dumps(fingerprint, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

@app.get("/api/playback/command")
def playback_command(
    db: Session = Depends(get_db),
    since_revision: int | None = Query(default=None, ge=0),
    since_hash: str | None = Query(default=None),
):
    command = _resolve_playback_command(db)
    command_hash = _playback_command_hash(command)
    revision = int(command.get("revision") or 0)
    same_revision = since_revision is not None and revision <= since_revision
    same_hash = since_hash is not None and since_hash == command_hash
    if same_revision and same_hash:
        return {"revision": revision, "hash": command_hash, "changed": False}
    return {"changed": True, "hash": command_hash, **command}


@app.get("/api/system/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(User).limit(1)).all()
    return {"status": "ok", "time": datetime.now(timezone.utc)}


def _host_control_request(action: str) -> dict[str, object]:
    token = str(settings.host_control_token or "").strip()
    if not token:
        raise HTTPException(status_code=503, detail="Host control token not configured")
    base_url = str(settings.host_control_url or "http://127.0.0.1:9510").rstrip("/")
    url = f"{base_url}/control/{action}"
    headers = {"X-SignalKiosk-Control-Token": token}
    try:
        with httpx.Client(timeout=15.0) as client:
            res = client.post(url, headers=headers)
        if res.status_code >= 400:
            raise HTTPException(status_code=res.status_code, detail=f"Host control rejected action '{action}'")
        data = res.json()
        if not isinstance(data, dict):
            return {"status": "ok", "action": action}
        return data
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Host control unavailable: {exc}") from exc


@app.get("/api/system/control/status")
def system_control_status(_: User = Depends(get_current_user)):
    token = str(settings.host_control_token or "").strip()
    if not token:
        return {"enabled": False, "detail": "Host control token not configured"}
    base_url = str(settings.host_control_url or "http://127.0.0.1:9510").rstrip("/")
    headers = {"X-SignalKiosk-Control-Token": token}
    try:
        with httpx.Client(timeout=5.0) as client:
            res = client.get(f"{base_url}/control/status", headers=headers)
        if res.status_code >= 400:
            return {"enabled": False, "detail": f"Host control returned {res.status_code}"}
        payload = res.json()
        if not isinstance(payload, dict):
            payload = {"status": "ok"}
        return {"enabled": True, **payload}
    except Exception as exc:
        return {"enabled": False, "detail": str(exc)}


@app.post("/api/system/control/restart-runner")
def restart_runner(_: User = Depends(get_current_user)):
    return _host_control_request("runner/restart")


@app.post("/api/system/control/restart-app")
def restart_app(_: User = Depends(get_current_user)):
    return _host_control_request("docker/restart-app")


@app.post("/api/system/control/restart-frontend")
def restart_frontend(_: User = Depends(get_current_user)):
    return _host_control_request("docker/restart-frontend")


@app.post("/api/system/control/restart-all")
def restart_all(_: User = Depends(get_current_user)):
    return _host_control_request("docker/restart-all")
