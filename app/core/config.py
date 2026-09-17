"""
Centralized application configuration.

Single Settings(BaseSettings) class, loaded once from `.env`, split into logical
nested groups (settings.db.url, settings.erp.base_url, ...) rather than many
separate files. Simpler for a modular monolith at this stage (Phase 5 §8).
"""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    url: str = Field(..., alias="DATABASE_URL")
    pool_size: int = Field(10, alias="DATABASE_POOL_SIZE")
    max_overflow: int = Field(20, alias="DATABASE_MAX_OVERFLOW")
    echo: bool = Field(False, alias="DATABASE_ECHO")


class JWTSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    secret: str = Field(..., alias="JWT_SECRET")
    algorithm: str = Field("HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(60, alias="JWT_ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(7, alias="JWT_REFRESH_TOKEN_EXPIRE_DAYS")


class ERPSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    base_url: str = Field("", alias="ERP_API_BASE_URL")
    api_key: str = Field("", alias="ERP_API_KEY")
    token_validate_path: str = Field("/auth/validate", alias="ERP_TOKEN_VALIDATE_PATH")
    login_path: str = Field("/auth/login", alias="ERP_LOGIN_PATH")
    webhook_timeout_sec: int = Field(10, alias="ERP_WEBHOOK_TIMEOUT_SEC")
    webhook_token: str = Field("", alias="ERP_WEBHOOK_TOKEN")


class StorageSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    backend: str = Field("local", alias="STORAGE_BACKEND")
    base_path: str = Field("./storage", alias="STORAGE_BASE_PATH")


class LoggingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    level: str = Field("INFO", alias="LOG_LEVEL")
    format: str = Field("json", alias="LOG_FORMAT")
    console_level: str = Field("WARNING", alias="CONSOLE_LOG_LEVEL")
    file_path: str = Field("logs/app.log", alias="LOG_FILE_PATH")


class NotificationSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    smtp_host: str = Field("", alias="SMTP_HOST")
    smtp_port: int = Field(587, alias="SMTP_PORT")
    smtp_user: str = Field("", alias="SMTP_USER")
    smtp_password: str = Field("", alias="SMTP_PASSWORD")
    smtp_from_email: str = Field("notifications@ns-exam.com", alias="SMTP_FROM_EMAIL")
    smtp_use_tls: bool = Field(True, alias="SMTP_USE_TLS")
    email_enabled: bool = Field(False, alias="EMAIL_NOTIFICATIONS_ENABLED")

    push_enabled: bool = Field(False, alias="PUSH_NOTIFICATIONS_ENABLED")
    push_api_key: str = Field("", alias="PUSH_API_KEY")
    push_gateway_url: str = Field("", alias="PUSH_GATEWAY_URL")


class Settings(BaseSettings):
    """
    Root settings object. Access nested config via:
        settings.db.url
        settings.jwt.secret
        settings.erp.base_url
        settings.notification.email_enabled
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = Field("exam-engine", alias="APP_NAME")
    app_env: str = Field("development", alias="APP_ENV")
    app_debug: bool = Field(True, alias="APP_DEBUG")
    app_version: str = Field("0.1.0", alias="APP_VERSION")

    cors_allowed_origins: str = Field("http://localhost:3000", alias="CORS_ALLOWED_ORIGINS")

    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    jwt: JWTSettings = Field(default_factory=JWTSettings)
    erp: ERPSettings = Field(default_factory=ERPSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    notification: NotificationSettings = Field(default_factory=NotificationSettings)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance - .env is read exactly once per process."""
    return Settings()


settings = get_settings()
