from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from functools import lru_cache
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

EMBEDDING_DIM = 1536
MIN_SECRET_KEY_LENGTH = 32

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    db_url: str
    test_db_url: str | None = None

    gemini_api_key: SecretStr
    gemini_model: str
    gemini_embedding_model: str
    llm_timeout_seconds: float = Field(default=30.0, gt=0)

    business_timezone: str = "UTC"

    agent_max_steps: int = Field(default=6, ge=1, le=20)
    agent_max_tool_retries: int = Field(default=2, ge=0, le=2)

    llm_input_price_per_1m_tokens: float = Field(default=0.0, ge=0)
    llm_output_price_per_1m_tokens: float = Field(default=0.0, ge=0)

    secret_key: SecretStr
    algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    access_token_expire_minutes: int = Field(default=30, ge=1, le=1440)

    public_chat_base_url: str = "http://localhost:8000"


    cors_allowed_origins: str = ""

    public_chat_rate_limit: int = Field(default=20, ge=1)
    public_chat_rate_window_seconds: int = Field(default=60, ge=1, le=86400)

    @field_validator("secret_key")
    @classmethod
    def _long_secret_key(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < MIN_SECRET_KEY_LENGTH:
            raise ValueError(
                f"SECRET_KEY must be at least {MIN_SECRET_KEY_LENGTH} characters; "
                "generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        return value

    @field_validator("public_chat_base_url")
    @classmethod
    def _http_base_url(cls, value: str) -> str:
        clean = value.strip().rstrip("/")
        if not clean.startswith(("http://", "https://")) or "?" in clean or "#" in clean:
            raise ValueError(
                "PUBLIC_CHAT_BASE_URL must be an http(s) URL without a query or fragment, "
                "like 'https://chat.example.com'"
            )
        return clean

    @field_validator("cors_allowed_origins")
    @classmethod
    def _origins(cls, value: str) -> str:
        for origin in _split_origins(value):
            scheme, _, rest = origin.partition("://")
            if scheme not in ("http", "https") or not rest or "/" in rest or "*" in origin:
                raise ValueError(
                    f"CORS_ALLOWED_ORIGINS entry {origin!r} must be an origin like "
                    "'http://localhost:5173' (scheme and host, no path, no wildcard)"
                )
        return value

    @property
    def cors_origins(self) -> list[str]:
        return _split_origins(self.cors_allowed_origins)

    @field_validator("business_timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Unknown time zone {value!r}; use an IANA name like 'Europe/London'") from exc
        return value

    @property
    def business_tz(self) -> ZoneInfo:
        return ZoneInfo(self.business_timezone)

def _split_origins(value: str) -> list[str]:
    return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

