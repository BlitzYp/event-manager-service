from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    app_name: str = "Event Manager Service"
    database_url: str = "mysql+pymysql://event_manager:change-me@localhost:3307/event_manager"
    app_secret_key: str = Field("development-only-change-this-secret-key", min_length=32)
    public_app_url: str = "http://localhost:3000"
    cookie_secure: bool = False
    admin_session_hours: int = 12
    vendor_session_idle_minutes: int = 30
    pending_payment_minutes: int = 5
    admin_wallet_preview_minutes: int = 5
    environment: str = "development"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str = "no-reply@example.com"
    smtp_from_name: str = "Event Manager"
    smtp_starttls: bool = True
    smtp_ssl: bool = False
    smtp_timeout_seconds: int = 20
    email_test_recipient: str | None = None
    development_email_delivery_limit: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
