from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    gameplay_host: str = "0.0.0.0"
    gameplay_port: int = 8090
    database_url: str = "postgresql+asyncpg://gameplay:gameplay@localhost:5432/gameplay"
    redis_url: str = "redis://localhost:6379/1"
    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: str = ""
    character_api_base_url: str = "http://localhost:8000"
    firebase_project_id: str = ""
    firebase_credentials_path: str = ""

    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
