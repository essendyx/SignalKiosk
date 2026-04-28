import json
from datetime import datetime, timezone, timedelta
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from .config import settings
from .db import get_db
from .deps import get_current_user
from .models import AuditLog, AuthProfile, Content, OverrideEvent, Preset, PresetItem, Schedule, SystemSetting, User, WebhookEndpoint
from .schemas import AuthProfileIn, AuthProfileOut, ContentIn, ContentListOut, ContentOut, LoginIn, PresetIn, PresetItemIn, PresetOut, ScheduleIn, ScheduleOut, SystemSettingIn, SystemSettingOut, TokenOut, WebhookIn, WebhookTriggerIn
from .security import create_access_token, decrypt_secret, encrypt_secret, hash_password, hash_token, verify_password
from .services import advance_rotation, ensure_playback_state

app = FastAPI(title="signalKiosk", version="1.1.0")


def _mask_auth_config(raw: dict[str, str]) -> dict[str, str]:
    masked: dict[str, str] = {}
    for key, value in raw.items():
        low = key.lower()
        if any(word in low for word in ["password", "token", "secret", "key", "cookie"]):
            masked[key] = "********"
        else:
            masked[key] = value
    return masked

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
    obj = Content(**payload.model_dump())
    db.add(obj)
    db.add(AuditLog(actor_type="user", actor_id=user.id, action="create", entity_type="content", entity_id=obj.id, metadata_json="{}"))
    db.commit()
    db.refresh(obj)
    return obj


@app.put("/api/contents/{content_id}", response_model=ContentOut)
def update_content(content_id: str, payload: ContentIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = db.get(Content, content_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    for key, value in payload.model_dump().items():
        setattr(obj, key, value)
    db.add(obj)
    db.add(AuditLog(actor_type="user", actor_id=user.id, action="update", entity_type="content", entity_id=obj.id, metadata_json="{}"))
    db.commit()
    db.refresh(obj)
    return obj


@app.post("/api/presets", response_model=PresetOut)
def create_preset(payload: PresetIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    if payload.is_default:
        db.query(Preset).update({Preset.is_default: False})
    obj = Preset(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@app.get("/api/presets", response_model=list[PresetOut])
def list_presets(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.execute(select(Preset).order_by(Preset.created_at.desc())).scalars().all()


@app.post("/api/presets/{preset_id}/items")
def add_preset_item(preset_id: str, payload: PresetItemIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    if not db.get(Preset, preset_id):
        raise HTTPException(status_code=404, detail="Preset not found")
    item = PresetItem(preset_id=preset_id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id}


@app.get("/api/schedules", response_model=list[ScheduleOut])
def list_schedules(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.execute(select(Schedule).order_by(Schedule.priority.desc())).scalars().all()


@app.post("/api/schedules", response_model=ScheduleOut)
def create_schedule(payload: ScheduleIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    if not db.get(Preset, payload.preset_id):
        raise HTTPException(status_code=400, detail="Invalid preset_id")
    obj = Schedule(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


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
    return {
        "mode": state.active_mode,
        "active_preset_id": state.active_preset_id,
        "active_content_id": state.active_content_id,
        "started_at": state.started_at,
        "ends_at": state.ends_at,
    }


@app.get("/playback", response_class=HTMLResponse)
def playback_page(db: Session = Depends(get_db)):
    state = advance_rotation(db, datetime.now(timezone.utc))
    if state.active_mode == "override":
        payload = json.loads(state.state_json or "{}")
        action = payload.get("action")
        if action == "play_url" and payload.get("url"):
            url = payload["url"]
            return f"<html><body style='margin:0'><iframe src='{url}' style='border:0;width:100vw;height:100vh'></iframe></body></html>"
        if action == "play_html":
            html = payload.get("html", "")
            return f"<html><body>{html}</body></html>"

    if not state.active_content_id:
        return "<html><body style='font-family: sans-serif; background:#111; color:#fff; display:flex; align-items:center; justify-content:center; height:100vh'>Fallback: Kein aktiver Inhalt</body></html>"
    content = db.get(Content, state.active_content_id)
    if not content:
        return "<html><body>Fehler: Inhalt nicht gefunden</body></html>"
    cfg = json.loads(content.config_json)
    if content.type == "webpage":
        return f"<html><body style='margin:0'><iframe src='{cfg.get('url','about:blank')}' style='border:0;width:100vw;height:100vh'></iframe></body></html>"
    if content.type == "image":
        return f"<html><body style='margin:0;background:#000'><img src='{cfg.get('url','')}' style='width:100vw;height:100vh;object-fit:contain'></body></html>"
    if content.type == "video":
        return f"<html><body style='margin:0;background:#000'><video src='{cfg.get('url','')}' autoplay muted controls style='width:100vw;height:100vh;object-fit:contain'></video></body></html>"
    if content.type == "html":
        return f"<html><body>{cfg.get('html','')}</body></html>"
    return "<html><body>Unbekannter Inhaltstyp</body></html>"


@app.get("/api/system/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(User).limit(1)).all()
    return {"status": "ok", "time": datetime.now(timezone.utc)}
