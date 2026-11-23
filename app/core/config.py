from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from functools import lru_cache
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
    embedding_dim: int
    llm_timeout_seconds: float = Field(default=30.0, gt=0)

    business_timezone: str = "UTC"

    agent_max_steps: int = Field(default=6, ge=1, le=20)
    agent_max_tool_retries: int = Field(default=2, ge=0, le=2)

    llm_input_price_per_1m_tokens: float = Field(default=0.0, ge=0)
    llm_output_price_per_1m_tokens: float = Field(default=0.0, ge=0)

    secret_key: SecretStr
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

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

@lru_cache
def get_settings() -> Settings:
    return Settings()

