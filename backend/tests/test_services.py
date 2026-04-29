from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import Content, OverrideEvent, Preset, PresetItem, Schedule
from app.services import evaluate_schedule, advance_rotation


def setup_db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def test_schedule_priority():
    db = setup_db()
    p1 = Preset(name="A", enabled=True, priority=1)
    p2 = Preset(name="B", enabled=True, priority=2)
    db.add_all([p1, p2])
    db.commit()
    db.add(Schedule(name="s1", preset_id=p1.id, weekdays="0,1,2,3,4,5,6", start_time="00:00", end_time="23:59", timezone="UTC", priority=10))
    db.add(Schedule(name="s2", preset_id=p2.id, weekdays="0,1,2,3,4,5,6", start_time="00:00", end_time="23:59", timezone="UTC", priority=20))
    db.commit()
    decision = evaluate_schedule(db, datetime.now(timezone.utc))
    assert decision.preset_id == p2.id


def test_override_wins():
    db = setup_db()
    now = datetime.now(timezone.utc)
    db.add(OverrideEvent(action="play_url", payload_json="{}", duration_seconds=30, priority=999, ends_at=now + timedelta(seconds=30)))
    db.commit()
    decision = evaluate_schedule(db, now)
    assert decision.mode == "override"


def test_rotation_picks_content():
    db = setup_db()
    c = Content(name="C", type="webpage", config_json='{"url":"https://example.org"}', default_duration_seconds=10)
    p = Preset(name="P", is_default=True)
    db.add_all([c, p])
    db.commit()
    db.add(PresetItem(preset_id=p.id, content_id=c.id, position=0, enabled=True))
    db.commit()
    state = advance_rotation(db, datetime.now(timezone.utc))
    assert state.active_content_id == c.id


def test_rotation_skips_deleted_content_from_preset_item():
    db = setup_db()
    c1 = Content(name="First", type="webpage", config_json='{"url":"https://example.org/1"}', default_duration_seconds=10)
    c2 = Content(name="Second", type="webpage", config_json='{"url":"https://example.org/2"}', default_duration_seconds=10)
    p = Preset(name="P", is_default=True)
    db.add_all([c1, c2, p])
    db.commit()

    db.add(PresetItem(preset_id=p.id, content_id=c1.id, position=0, duration_seconds=10, enabled=True))
    db.add(PresetItem(preset_id=p.id, content_id=c2.id, position=1, duration_seconds=10, enabled=True))
    db.commit()

    db.query(PresetItem).filter(PresetItem.content_id == c1.id).delete(synchronize_session=False)
    db.delete(c1)
    db.commit()

    state = advance_rotation(db, datetime.now(timezone.utc))
    assert state.active_content_id == c2.id
