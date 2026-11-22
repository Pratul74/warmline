from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from functools import lru_cache
from typing import Literal

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
    openai_model: str
    embedding_dim: int
    coarena_api_key: SecretStr
    coarena_base_url: str
    llm_timeout_seconds: float = Field(default=30.0, gt=0)

    agent_max_steps: int = Field(default=6, ge=1, le=20)
    agent_max_tool_retries: int = Field(default=2, ge=0, le=2)

    llm_input_price_per_1m_tokens: float = Field(default=0.0, ge=0)
    llm_output_price_per_1m_tokens: float = Field(default=0.0, ge=0)

    secret_key: SecretStr
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

@lru_cache
def get_settings() -> Settings:
    return Settings()

