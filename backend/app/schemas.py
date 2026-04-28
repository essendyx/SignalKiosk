from datetime import datetime
from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ContentIn(BaseModel):
    name: str
    type: str
    description: str | None = None
    enabled: bool = True
    config_json: str = "{}"
    default_duration_seconds: int = Field(default=15, ge=1, le=86400)
    fallback_content_id: str | None = None


class ContentOut(ContentIn):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ContentListOut(BaseModel):
    items: list[ContentOut]
    total: int
    page: int
    page_size: int


class PresetItemIn(BaseModel):
    content_id: str
    position: int = 0
    duration_seconds: int | None = Field(default=None, ge=1, le=86400)
    play_until_end: bool = False
    enabled: bool = True
    transition: str | None = None


class PresetItemOut(PresetItemIn):
    id: str
    preset_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PresetIn(BaseModel):
    name: str
    description: str | None = None
    enabled: bool = True
    is_default: bool = False
    loop_mode: bool = True
    shuffle: bool = False
    priority: int = 0


class PresetOut(PresetIn):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ScheduleIn(BaseModel):
    name: str
    preset_id: str
    enabled: bool = True
    weekdays: str = "0,1,2,3,4,5,6"
    start_time: str = "00:00"
    end_time: str = "23:59"
    start_date: str | None = None
    end_date: str | None = None
    timezone: str = "UTC"
    priority: int = 0


class ScheduleOut(ScheduleIn):
    id: str

    class Config:
        from_attributes = True


class WebhookIn(BaseModel):
    name: str
    slug: str
    token: str
    allowed_actions: list[str]
    enabled: bool = True


class WebhookTriggerIn(BaseModel):
    action: str
    url: str | None = None
    content_id: str | None = None
    preset_id: str | None = None
    duration_seconds: int = Field(default=60, ge=1, le=86400)
    mode: str = "replace_current"
    priority: int = 100
    return_to_previous: bool = True


class AuthProfileIn(BaseModel):
    name: str
    type: str
    config: dict[str, str]


class AuthProfileOut(BaseModel):
    id: str
    name: str
    type: str
    config_masked: dict[str, str]
    created_at: datetime
    updated_at: datetime


class SystemSettingIn(BaseModel):
    key: str
    value: dict[str, str | int | bool | float | None]


class SystemSettingOut(BaseModel):
    key: str
    value: dict[str, str | int | bool | float | None]
    updated_at: datetime
