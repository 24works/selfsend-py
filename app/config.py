from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    SELFSEND_HOST: str = "127.0.0.1"
    SELFSEND_PORT: int = 8787
    SELFSEND_LOG_LEVEL: str = "INFO"
    SELFSEND_API_KEYS: str = ""
    SELFSEND_FORCE_FROM: str = ""
    SELFSEND_ALLOWED_FROM_DOMAINS: str = ""
    SELFSEND_RATE_LIMIT_PER_MINUTE: int = 60
    SELFSEND_MAX_RECIPIENTS: int = 50
    SELFSEND_MAX_BODY_BYTES: int = 2 * 1024 * 1024

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_STARTTLS: bool = True
    SMTP_SSL: bool = False
    SMTP_TIMEOUT_SECONDS: int = 30

    @property
    def api_keys(self) -> list[str]:
        return [key.strip() for key in self.SELFSEND_API_KEYS.split(",") if key.strip()]

    @property
    def allowed_from_domains(self) -> list[str]:
        return [
            domain.strip().lower().lstrip("@")
            for domain in self.SELFSEND_ALLOWED_FROM_DOMAINS.split(",")
            if domain.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
