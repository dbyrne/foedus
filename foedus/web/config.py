"""Env-driven configuration for foedus.web."""
from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FOEDUS_", env_file=".env",
                                      extra="ignore")

    database_url: str = "sqlite:///./foedus_web.db"
    session_secret: str = "dev-only-change-me"
    jwt_secret: str = "dev-only-change-me-jwt"
    jwt_ttl_seconds: int = 3600
    github_oauth_client_id: str = ""
    github_oauth_client_secret: str = ""
    base_url: str = "http://localhost:8000"   # external URL, used for OAuth callback
    deadline_tick_seconds: int = 60

def get_settings() -> Settings:
    return Settings()
