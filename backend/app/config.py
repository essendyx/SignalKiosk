from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "production"
    app_secret_key: str = "change-me"
    secret_encryption_key: str = ""
    database_url: str = "sqlite:////data/localkiosk.db"
    tz: str = "Europe/Berlin"
    log_level: str = "INFO"
    cors_allowed_origins: str = ""
    default_admin_username: str = "admin"
    default_admin_password: str = "admin123!"
    playback_debug_mode: bool = False

    @property
    def cors_origins(self) -> list[str]:
        if not self.cors_allowed_origins:
            return []
        return [item.strip() for item in self.cors_allowed_origins.split(",") if item.strip()]


settings = Settings()


def encryption_key_path() -> Path:
    return Path("/config/secret_encryption_key")
