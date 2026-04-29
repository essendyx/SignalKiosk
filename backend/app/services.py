import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import Content, OverrideEvent, PlaybackState, Preset, PresetItem, Schedule, SystemSetting


@dataclass
class PlaybackDecision:
    mode: str
    preset_id: str | None
    reason: str


def evaluate_schedule(db: Session, now_utc: datetime) -> PlaybackDecision:
    active_override = db.execute(
        select(OverrideEvent).where(OverrideEvent.status == "active", OverrideEvent.ends_at > now_utc).order_by(OverrideEvent.priority.desc())
    ).scalars().first()
    if active_override:
        return PlaybackDecision(mode="override", preset_id=None, reason="active override")

    schedules = db.execute(select(Schedule).where(Schedule.enabled.is_(True))).scalars().all()
    best: tuple[int, str] | None = None
    for sch in schedules:
        tz = ZoneInfo(sch.timezone)
        local_now = now_utc.astimezone(tz)
        if str(local_now.weekday()) not in sch.weekdays.split(","):
            continue
        hhmm = local_now.strftime("%H:%M")
        if not (sch.start_time <= hhmm <= sch.end_time):
            continue
        if best is None or sch.priority > best[0]:
            best = (sch.priority, sch.preset_id)
    if best:
        return PlaybackDecision(mode="schedule", preset_id=best[1], reason="highest priority schedule")

    default = db.execute(select(Preset).where(Preset.is_default.is_(True), Preset.enabled.is_(True))).scalars().first()
    if default:
        return PlaybackDecision(mode="default", preset_id=default.id, reason="default preset")
    return PlaybackDecision(mode="fallback", preset_id=None, reason="no active preset")


def ensure_playback_state(db: Session) -> PlaybackState:
    state = db.get(PlaybackState, 1)
    if state:
        return state
    state = PlaybackState(id=1, active_mode="fallback", state_json="{}")
    db.add(state)
    db.commit()
    db.refresh(state)
    return state


def _get_playback_revision(db: Session) -> int:
    rev = db.get(SystemSetting, "playback.revision")
    if not rev:
        return 0
    try:
        payload = json.loads(rev.value_json or "{}")
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0
    try:
        return int(payload.get("value", 0))
    except Exception:
        return 0


def _promote_next_queued_override(db: Session, now_utc: datetime) -> None:
    active_override = db.execute(
        select(OverrideEvent).where(OverrideEvent.status == "active", OverrideEvent.ends_at > now_utc)
    ).scalars().first()
    if active_override:
        return
    queued = db.execute(
        select(OverrideEvent).where(OverrideEvent.status == "queued").order_by(OverrideEvent.created_at.asc())
    ).scalars().first()
    if not queued:
        return
    queued.status = "active"
    queued.started_at = now_utc
    queued.ends_at = now_utc + timedelta(seconds=queued.duration_seconds)
    db.add(queued)
    db.commit()


def advance_rotation(db: Session, now_utc: datetime) -> PlaybackState:
    state = ensure_playback_state(db)
    state_data = json.loads(state.state_json or "{}") if state.state_json else {}
    if not isinstance(state_data, dict):
        state_data = {}
    current_revision = _get_playback_revision(db)
    state_revision = int(state_data.get("playback_revision", 0) or 0)
    force_refresh = current_revision != state_revision
    ends_at = state.ends_at
    if ends_at and ends_at.tzinfo is None:
        now_cmp = now_utc.replace(tzinfo=None)
    else:
        now_cmp = now_utc
    if (not force_refresh) and ends_at and now_cmp < ends_at and state.active_content_id:
        return state

    _promote_next_queued_override(db, now_utc)

    decision = evaluate_schedule(db, now_utc)
    state.active_mode = decision.mode
    state.active_preset_id = decision.preset_id

    if decision.mode == "override":
        ov = db.execute(select(OverrideEvent).where(OverrideEvent.status == "active", OverrideEvent.ends_at > now_utc).order_by(OverrideEvent.priority.desc())).scalars().first()
        if ov:
            payload = json.loads(ov.payload_json)
            payload["reason"] = decision.reason
            payload["playback_revision"] = current_revision
            state.active_override_id = ov.id
            state.active_content_id = payload.get("content_id")
            state.started_at = now_utc
            state.ends_at = ov.ends_at
            state.state_json = json.dumps(payload)
    elif decision.preset_id:
        items = db.execute(
            select(PresetItem).where(PresetItem.preset_id == decision.preset_id, PresetItem.enabled.is_(True)).order_by(PresetItem.position.asc())
        ).scalars().all()
        if items:
            state_data = json.loads(state.state_json or "{}")
            if not isinstance(state_data, dict):
                state_data = {}
            previous_preset_id = state_data.get("preset_id")
            previous_index = int(state_data.get("item_index", -1))
            if previous_preset_id != decision.preset_id:
                next_index = 0
            elif force_refresh:
                next_index = previous_index if previous_index >= 0 else 0
            else:
                next_index = previous_index + 1

            preset = db.get(Preset, decision.preset_id)
            if preset and preset.shuffle and not force_refresh:
                next_index = int(now_utc.timestamp()) % len(items)
            elif next_index >= len(items):
                if preset and preset.loop_mode:
                    next_index = 0
                else:
                    next_index = len(items) - 1

            pick = items[next_index]
            content_obj = db.get(Content, pick.content_id)
            if not content_obj:
                state.active_content_id = None
                state.active_override_id = None
                state.started_at = now_utc
                state.ends_at = None
                state.state_json = json.dumps({"reason": "preset references missing content"})
                db.add(state)
                db.commit()
                db.refresh(state)
                return state

            duration = pick.duration_seconds or content_obj.default_duration_seconds
            state.active_content_id = pick.content_id
            state.active_override_id = None
            state.started_at = now_utc
            state.ends_at = now_utc + timedelta(seconds=duration)
            state.state_json = json.dumps({"reason": decision.reason, "preset_id": decision.preset_id, "item_index": next_index, "playback_revision": current_revision})
        else:
            state.active_content_id = None
            state.ends_at = None
            state.state_json = json.dumps({"reason": "preset has no items", "playback_revision": current_revision})
    else:
        state.active_content_id = None
        state.active_override_id = None
        state.started_at = now_utc
        state.ends_at = None
        state.state_json = json.dumps({"reason": "fallback", "playback_revision": current_revision})

    db.add(state)
    db.commit()
    db.refresh(state)
    return state
