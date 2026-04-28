import json
import html
import os
import re
import uuid
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit
import re
from datetime import datetime, timezone, timedelta
from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
import httpx

CURRENT_PROXY_ORIGIN: str | None = None
CURRENT_PROXY_BASE_PATH: str = "/"
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from .config import settings
from .db import get_db
from .deps import get_current_user
from .models import AuditLog, AuthProfile, Content, OverrideEvent, Preset, PresetItem, Schedule, SystemSetting, User, WebhookEndpoint
from .schemas import AuthProfileIn, AuthProfileOut, ContentIn, ContentListOut, ContentOut, LoginIn, PresetIn, PresetItemIn, PresetItemOut, PresetOut, ScheduleIn, ScheduleOut, SystemSettingIn, SystemSettingOut, TokenOut, WebhookIn, WebhookTriggerIn
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
        mode = str(cfg.get("webpage_mode", "embedded")).strip().lower()
        if mode not in {"embedded", "direct"}:
            mode = "embedded"
        cfg = {"url": url, "webpage_mode": mode}
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


def _url_is_probably_frame_blocked(url: str) -> bool:
    try:
        with httpx.Client(follow_redirects=True, timeout=5.0) as client:
            response = client.get(url)
        xfo = response.headers.get("x-frame-options", "").lower()
        if "deny" in xfo or "sameorigin" in xfo:
            return True
        csp = response.headers.get("content-security-policy", "").lower()
        if "frame-ancestors" in csp and "*" not in csp:
            if "'self'" in csp or "'none'" in csp:
                return True
    except Exception:
        return False
    return False


def _to_site_proxy_path(absolute_url: str) -> str:
    if not CURRENT_PROXY_ORIGIN:
        return "/"
    parsed = urlsplit(absolute_url)
    base = urlsplit(CURRENT_PROXY_ORIGIN)
    if parsed.scheme != base.scheme or parsed.netloc != base.netloc:
        return "/playback/proxy-asset?target=" + quote(absolute_url, safe="")
    suffix = parsed.path or "/"
    if parsed.query:
        suffix = f"{suffix}?{parsed.query}"
    return f"/playback/site{suffix}"


def _rewrite_html_for_proxy(html_text: str, base_url: str) -> str:
    attr_pattern = re.compile(r"(src|href)=['\"]([^'\"]+)['\"]", re.IGNORECASE)

    def repl(match: re.Match[str]) -> str:
        attr = match.group(1)
        value = match.group(2)
        if value.startswith(("data:", "javascript:", "mailto:", "#")):
            return match.group(0)
        absolute = urljoin(base_url, value)
        proxied = _to_site_proxy_path(absolute)
        return f'{attr}="{proxied}"'

    rewritten = attr_pattern.sub(repl, html_text)
    rewritten = rewritten.replace('"/socket.io', '"/playback/site/socket.io')
    rewritten = rewritten.replace("'/socket.io", "'/playback/site/socket.io")
    return rewritten


def _set_proxy_origin(target_url: str) -> None:
    global CURRENT_PROXY_ORIGIN, CURRENT_PROXY_BASE_PATH
    parts = urlsplit(target_url)
    if parts.scheme and parts.netloc:
        CURRENT_PROXY_ORIGIN = f"{parts.scheme}://{parts.netloc}"
        CURRENT_PROXY_BASE_PATH = parts.path or "/"


async def _proxy_to_current_origin(path: str, request: Request) -> Response:
    if not CURRENT_PROXY_ORIGIN:
        raise HTTPException(status_code=404, detail="No active playback proxy target")

    query = request.url.query
    url = f"{CURRENT_PROXY_ORIGIN}{path}"
    if query:
        url = f"{url}?{query}"

    headers = {k: v for k, v in request.headers.items() if k.lower() not in {"host", "content-length"}}
    headers["origin"] = CURRENT_PROXY_ORIGIN
    headers["referer"] = CURRENT_PROXY_ORIGIN + "/"
    body = await request.body()
    with httpx.Client(follow_redirects=True, timeout=20.0) as client:
        res = client.request(request.method, url, headers=headers, content=body)
    excluded = {"content-encoding", "transfer-encoding", "connection"}
    out_headers = {k: v for k, v in res.headers.items() if k.lower() not in excluded}
    return Response(content=res.content, status_code=res.status_code, media_type=res.headers.get("content-type"), headers=out_headers)


@app.api_route("/playback/site", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@app.api_route("/playback/site/{site_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def playback_site_proxy(request: Request, site_path: str = ""):
    path = "/" + site_path if site_path else CURRENT_PROXY_BASE_PATH
    return await _proxy_to_current_origin(path, request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.post("/api/webhooks")
def create_webhook(payload: WebhookIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    endpoint = WebhookEndpoint(
        name=payload.name,
        slug=payload.slug,
        token_hash=hash_token(payload.token),
        allowed_actions=",".join(payload.allowed_actions),
        enabled=payload.enabled,
    )
    db.add(endpoint)
    db.commit()
    db.refresh(endpoint)
    return {"id": endpoint.id, "slug": endpoint.slug}


@app.put("/api/webhooks/{webhook_id}")
def update_webhook(webhook_id: str, payload: WebhookIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    endpoint = db.get(WebhookEndpoint, webhook_id)
    if not endpoint:
        raise HTTPException(status_code=404, detail="Not found")
    endpoint.name = payload.name
    endpoint.slug = payload.slug
    endpoint.token_hash = hash_token(payload.token)
    endpoint.allowed_actions = ",".join(payload.allowed_actions)
    endpoint.enabled = payload.enabled
    db.add(endpoint)
    db.commit()
    db.refresh(endpoint)
    return {"id": endpoint.id, "slug": endpoint.slug}


@app.delete("/api/webhooks/{webhook_id}")
def delete_webhook(webhook_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    endpoint = db.get(WebhookEndpoint, webhook_id)
    if not endpoint:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(endpoint)
    db.commit()
    return {"status": "deleted"}


@app.get("/api/webhooks")
def list_webhooks(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.execute(select(WebhookEndpoint).order_by(WebhookEndpoint.created_at.desc())).scalars().all()
    return [{"id": w.id, "name": w.name, "slug": w.slug, "enabled": w.enabled, "allowed_actions": w.allowed_actions.split(",")} for w in rows]


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


@app.post("/webhook/{slug}")
def webhook(slug: str, payload: WebhookTriggerIn, token: str = Query(default=""), db: Session = Depends(get_db)):
    endpoint = db.execute(select(WebhookEndpoint).where(WebhookEndpoint.slug == slug, WebhookEndpoint.enabled.is_(True))).scalars().first()
    if not endpoint:
        raise HTTPException(status_code=404, detail="Webhook endpoint not found")
    if endpoint.token_hash != hash_token(token):
        raise HTTPException(status_code=401, detail="Invalid token")
    allowed = set(endpoint.allowed_actions.split(","))
    if payload.action not in allowed:
        raise HTTPException(status_code=403, detail="Action not allowed")

    now = datetime.now(timezone.utc)
    ends = now + timedelta(seconds=payload.duration_seconds)
    event = OverrideEvent(
        source_webhook_id=endpoint.id,
        action=payload.action,
        payload_json=json.dumps(payload.model_dump()),
        duration_seconds=payload.duration_seconds,
        priority=payload.priority,
        ends_at=ends,
    )
    db.add(event)
    db.commit()

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
    rev = db.get(SystemSetting, "playback.revision")
    revision = 0
    if rev:
        try:
            revision = int(json.loads(rev.value_json).get("value", 0))
        except Exception:
            revision = 0
    return {
        "active_content_id": state.active_content_id,
        "active_mode": state.active_mode,
        "ends_at": state.ends_at.isoformat() if state.ends_at else None,
        "revision": revision,
    }


@app.get("/playback/proxy", response_class=HTMLResponse)
def playback_proxy(target: str = Query(default="")):
    if not target.startswith("http://") and not target.startswith("https://"):
        raise HTTPException(status_code=400, detail="Invalid target URL")
    try:
        _set_proxy_origin(target)
        with httpx.Client(follow_redirects=True, timeout=12.0) as client:
            res = client.get(target)
        content_type = res.headers.get("content-type", "text/html")
        text = res.text
        if "text/html" in content_type.lower():
            text = _rewrite_html_for_proxy(text, str(res.url))
        excluded = {"content-encoding", "transfer-encoding", "connection", "content-length", "x-frame-options", "content-security-policy", "frame-options"}
        out_headers = {k: v for k, v in res.headers.items() if k.lower() not in excluded}
        return HTMLResponse(content=text, status_code=res.status_code, headers=out_headers)
    except Exception as exc:
        return HTMLResponse(content=f"<html><body>Proxy-Fehler: {html.escape(str(exc))}</body></html>", status_code=502)


@app.get("/playback/proxy-asset")
def playback_proxy_asset(target: str = Query(default="")):
    if not target.startswith("http://") and not target.startswith("https://"):
        raise HTTPException(status_code=400, detail="Invalid target URL")
    try:
        with httpx.Client(follow_redirects=True, timeout=15.0) as client:
            res = client.get(target)
        content_type = res.headers.get("content-type", "application/octet-stream")
        excluded = {"content-encoding", "transfer-encoding", "connection", "content-length", "x-frame-options", "content-security-policy", "frame-options"}
        out_headers = {k: v for k, v in res.headers.items() if k.lower() not in excluded}
        return Response(content=res.content, media_type=content_type, headers=out_headers)
    except Exception as exc:
        return Response(content=f"Proxy-Asset-Fehler: {str(exc)}".encode("utf-8"), media_type="text/plain", status_code=502)


@app.api_route("/socket.io", methods=["GET", "POST"])
@app.api_route("/socket.io/{rest:path}", methods=["GET", "POST"])
async def playback_proxy_socket(request: Request, rest: str = ""):
    path = "/socket.io" + (f"/{rest}" if rest else "")
    return await _proxy_to_current_origin(path, request)


@app.api_route("/playback/{asset_path:path}", methods=["GET", "POST"])
async def playback_proxy_playback_assets(request: Request, asset_path: str):
    if asset_path == "":
        raise HTTPException(status_code=404, detail="Not found")
    path = f"/playback/{asset_path}"
    proxied = await _proxy_to_current_origin(path, request)
    ctype = (proxied.media_type or "").lower()
    if asset_path.endswith(".js") and "text/html" in ctype:
        fallback_path = f"/{asset_path}"
        return await _proxy_to_current_origin(fallback_path, request)
    return proxied


def _build_playback_fragment(db: Session) -> dict[str, str | None]:
    state = advance_rotation(db, datetime.now(timezone.utc))
    if state.active_mode == "override":
        try:
            payload = json.loads(state.state_json or "{}")
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        action = payload.get("action")
        if action == "play_url" and payload.get("url"):
            url = str(payload["url"])
            src = "/playback/proxy?target=" + quote(url, safe="") if _url_is_probably_frame_blocked(url) else url
            return {"mode": state.active_mode, "active_content_id": state.active_content_id, "ends_at": state.ends_at.isoformat() if state.ends_at else None, "html": f"<iframe src='{src}' style='border:0;width:100vw;height:100vh'></iframe>"}
        if action == "play_html":
            return {"mode": state.active_mode, "active_content_id": state.active_content_id, "ends_at": state.ends_at.isoformat() if state.ends_at else None, "html": str(payload.get("html", ""))}

    if not state.active_content_id:
        return {"mode": state.active_mode, "active_content_id": None, "ends_at": state.ends_at.isoformat() if state.ends_at else None, "html": "<div style='font-family:sans-serif;background:#111;color:#fff;display:flex;align-items:center;justify-content:center;height:100vh'>Fallback: Kein aktiver Inhalt</div>"}

    content = db.get(Content, state.active_content_id)
    if not content:
        return {"mode": state.active_mode, "active_content_id": state.active_content_id, "ends_at": state.ends_at.isoformat() if state.ends_at else None, "html": "<div style='font-family:sans-serif;padding:18px'>Fehler: Inhalt nicht gefunden</div>"}

    try:
        cfg = json.loads(content.config_json)
    except Exception:
        cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}

    ctype = str(content.type or "").strip().lower()

    if ctype == "webpage":
        src = str(cfg.get("url", "about:blank"))
        webpage_mode = str(cfg.get("webpage_mode", "embedded")).strip().lower()
        if webpage_mode == "direct" and src:
            _set_proxy_origin(src)
            src = "/playback/site"
        elif src and _url_is_probably_frame_blocked(src):
            _set_proxy_origin(src)
            src = "/playback/proxy?target=" + quote(src, safe="")
        html_fragment = f"<iframe src='{src}' style='border:0;width:100vw;height:100vh'></iframe>"
    elif ctype == "image":
        src = str(cfg.get("asset_path") or cfg.get("url", ""))
        html_fragment = f"<img src='{src}' style='width:100vw;height:100vh;object-fit:contain'>"
    elif ctype == "video":
        src = str(cfg.get("asset_path") or cfg.get("url", ""))
        html_fragment = f"<video src='{src}' autoplay muted controls style='width:100vw;height:100vh;object-fit:contain'></video>"
    elif ctype == "html":
        html_fragment = str(cfg.get("html", ""))
    else:
        html_fragment = f"<div style='font-family:sans-serif;color:#fff;background:#111;height:100vh;display:flex;align-items:center;justify-content:center;padding:18px'>Unbekannter Inhaltstyp: {html.escape(str(content.type))}</div>"

    return {"mode": state.active_mode, "active_content_id": state.active_content_id, "ends_at": state.ends_at.isoformat() if state.ends_at else None, "html": html_fragment}


@app.get("/api/playback/render")
def playback_render(db: Session = Depends(get_db)):
    return _build_playback_fragment(db)


@app.get("/playback", response_class=HTMLResponse)
def playback_page(request: Request, db: Session = Depends(get_db)):
    try:
        initial = _build_playback_fragment(db)
        initial_sig = {
            "active_mode": initial.get("mode"),
            "active_content_id": initial.get("active_content_id"),
            "ends_at": initial.get("ends_at"),
        }
        return (
            "<html><body style='margin:0;background:#000;overflow:hidden'>"
            "<div id='root' style='width:100vw;height:100vh'></div>"
            "<div id='countdown' style='position:fixed;top:10px;right:10px;z-index:9999;padding:6px 10px;border-radius:8px;background:rgba(0,0,0,.55);color:#fff;font-family:Arial,sans-serif;font-size:14px;line-height:1;pointer-events:none'></div>"
            "<script>"
            f"let last={json.dumps(initial_sig)};"
            "let countdownTimer=null;"
            "function parseEndsAt(endsAt){"
            "if(!endsAt) return null;"
            "const raw=String(endsAt);"
            "const hasTz=/[zZ]|[+-]\\d\\d:\\d\\d$/.test(raw);"
            "const normalized=hasTz?raw:(raw+'Z');"
            "const ts=Date.parse(normalized);"
            "return Number.isNaN(ts)?null:ts;"
            "}"
            "function formatRemaining(endsAt){"
            "const ts=parseEndsAt(endsAt);"
            "if(ts===null) return '';"
            "const diff=Math.max(0,Math.ceil((ts-Date.now())/1000));"
            "return String(diff);"
            "}"
            "function updateCountdown(){"
            "const el=document.getElementById('countdown');"
            "if(!el) return;"
            "const t=formatRemaining(last.ends_at);"
            "el.textContent=t ? (t + ' Sek') : '';"
            "el.style.display=t ? 'block' : 'none';"
            "}"
            "function startCountdown(){"
            "if(countdownTimer!==null) clearInterval(countdownTimer);"
            "updateCountdown();"
            "countdownTimer=setInterval(updateCountdown,1000);"
            "}"
            f"document.getElementById('root').innerHTML={json.dumps(initial.get('html', ''))};"
            "startCountdown();"
            "async function tick(){"
            "try{"
            "const s=await fetch('/api/playback/public-status');const status=await s.json();"
            "const next={active_mode:status.active_mode,active_content_id:status.active_content_id,ends_at:status.ends_at};"
            "if(JSON.stringify(next)!==JSON.stringify(last)){"
            "const r=await fetch('/api/playback/render');const data=await r.json();"
            "document.getElementById('root').innerHTML=String(data.html||'');"
            "last={active_mode:data.mode,active_content_id:data.active_content_id,ends_at:data.ends_at};"
            "updateCountdown();"
            "}"
            "}catch(e){}"
            "}"
            "setInterval(tick,3000);"
            "</script></body></html>"
        )
    except Exception as exc:
        return f"<html><body style='font-family:sans-serif;padding:18px'>Playback Fehler: {html.escape(str(exc))}</body></html>"


@app.get("/api/system/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(User).limit(1)).all()
    return {"status": "ok", "time": datetime.now(timezone.utc)}
