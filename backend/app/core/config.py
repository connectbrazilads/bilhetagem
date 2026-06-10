from functools import lru_cache
from typing import Any, Union

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Sistema de Bilhetagem"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://printbilling:printbilling@localhost:5432/printbilling"
    secret_key: str = Field(default="change-me-in-production", min_length=16)
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    cors_origins: Union[str, list[str]] = ["http://localhost:3000"]
    default_monthly_quota: int = 500
    auto_create_users: bool = True
    auto_create_printers: bool = True
    safe_release_enabled: bool = True
    snmp_community: str = "public"
    snmp_timeout_seconds: float = 2.0
    snmp_retries: int = 1
    backend_snmp_poller_enabled: bool = False
    initial_admin_username: str = "admin"
    initial_admin_password: str = "admin12345"
    initial_agent_username: str = "agent"
    initial_agent_password: str = "agent12345"
    agent_latest_version: str = "0.2.0"
    agent_download_dir: str = "agent_downloads"
    agent_download_filename: str = "PrintBillingAgent.exe"
    agent_release_manifest_filename: str = "manifest.json"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> Union[str, list[str]]:
        if isinstance(v, str):
            import json
            v_stripped = v.strip()
            if not v_stripped:
                return []
            if v_stripped.startswith("[") and v_stripped.endswith("]"):
                try:
                    return json.loads(v_stripped)
                except Exception:
                    pass
            return [i.strip() for i in v_stripped.split(",") if i.strip()]
        return v

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
