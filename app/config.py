from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Microsoft Graph / Entra ID
    tenant_id: str
    client_id: str
    client_secret: str
    sender_user_principal_name: str

    # Webhook/subscription
    public_base_url: str
    graph_client_state: str

    # Gemini
    gemini_api_key: str
    gemini_model: str = "gemini-1.5-flash"

    # App
    db_path: str = "./data/app.db"
    app_base_url: str = "http://localhost:8000"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
