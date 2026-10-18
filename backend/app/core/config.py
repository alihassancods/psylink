from functools import lru_cache

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
