from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Mode
    # - gmail_imap: Send via Gmail SMTP + read replies via IMAP polling
    # - graph: Send/read/subscribe via Microsoft Graph webhooks (original mode)
    mail_mode: str = "gmail_imap"

    # Gmail (SMTP + IMAP)
    gmail_address: str | None = None
    gmail_app_password: str | None = None
    gmail_imap_host: str = "imap.gmail.com"
    gmail_imap_port: int = 993
    gmail_smtp_host: str = "smtp.gmail.com"
    gmail_smtp_port: int = 587

    # Polling (gmail_imap)
    poll_enabled: bool = True
    poll_interval_seconds: int = 60

    # Teams meeting creation (Microsoft Graph / Entra ID)
    teams_tenant_id: str | None = None
    teams_client_id: str | None = None
    teams_client_secret: str | None = None
    teams_organizer_upn: str | None = None

    # Legacy Microsoft Graph mail/webhook settings (only needed if mail_mode=graph)
    tenant_id: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    sender_user_principal_name: str | None = None

    # Webhook/subscription (mail_mode=graph)
    public_base_url: str | None = None
    graph_client_state: str = "change-me"

    # Gemini
    gemini_api_key: str
    gemini_model: str = "gemini-1.5-flash"

    # App
    db_path: str = "./data/app.db"
    app_base_url: str = "http://localhost:8000"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
