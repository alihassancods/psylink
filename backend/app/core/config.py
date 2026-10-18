from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "backend"
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://backend:backend@127.0.0.1:5433/backend"

    # Supabase JWT verification. Set exactly one key source: the JWKS URI for hosted
    # projects (RS256) or the JWT secret for self-hosted/legacy GoTrue (HS256).
    supabase_jwks_uri: str = ""
    supabase_jwt_secret: str = ""
    supabase_jwt_audience: str = "authenticated"
    supabase_issuer: str = ""

    # --- Speech to text (AssemblyAI) ----------------------------------------------------------
    # Keys are read from the environment only; never hardcode, never log them.
    assemblyai_api_key: str = ""
    # Upload guardrails. MAX_AUDIO_MB is enforced before/at the HTTP body; MAX_AUDIO_SECONDS
    # is enforced against the duration AssemblyAI reports back, because raw MediaRecorder
    # bytes carry no cheaply parseable duration and AssemblyAI's own ceiling (10 h) is far
    # above ours. Bounds below fail a misconfigured integer at startup, not at first upload.
    max_audio_seconds: int = 120
    max_audio_mb: int = 10

    # --- LLM analysis (Command Code Provider API, OpenAI-compatible) --------------------------
    commandcode_api_key: str = ""
    commandcode_base_url: str = "https://api.commandcode.ai/provider/v1"
    commandcode_model: str = "deepseek/deepseek-v4-flash"
    commandcode_fallback_model: str = ""

    @field_validator("max_audio_seconds")
    @classmethod
    def _audio_seconds_in_range(cls, value: int) -> int:
        if not 5 <= value <= 600:
            raise ValueError("MAX_AUDIO_SECONDS must be between 5 and 600")
        return value

    @field_validator("max_audio_mb")
    @classmethod
    def _audio_mb_in_range(cls, value: int) -> int:
        if not 1 <= value <= 25:
            raise ValueError("MAX_AUDIO_MB must be between 1 and 25")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
