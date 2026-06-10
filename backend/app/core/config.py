from functools import lru_cache
from typing import Any, Literal, Union

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET_KEY = "change-me-in-production"
DEFAULT_DATABASE_URL = "postgresql+psycopg://printbilling:printbilling@localhost:5432/printbilling"
DEFAULT_DATABASE_CREDENTIALS = "://printbilling:printbilling@"


class Settings(BaseSettings):
    app_name: str = "Sistema de Bilhetagem"
    environment: str = "development"
    database_url: str = DEFAULT_DATABASE_URL
    secret_key: str = Field(default=DEFAULT_SECRET_KEY, min_length=16)
    algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    access_token_expire_minutes: int = Field(default=60, ge=5, le=1440)
    cors_origins: Union[str, list[str]] = ["http://localhost:3000"]
    default_monthly_quota: int = Field(default=500, ge=0, le=1_000_000)
    auto_create_users: bool = True
    auto_create_printers: bool = True
    safe_release_enabled: bool = True
    web_print_max_upload_mb: int = Field(default=50, ge=1, le=512)
    web_print_upload_dir: str = "uploads"
    snmp_community: str = "public"
    snmp_timeout_seconds: float = Field(default=2.0, ge=0.1, le=30.0)
    snmp_retries: int = Field(default=1, ge=0, le=5)
    backend_snmp_poller_enabled: bool = False
    initial_admin_username: str = "admin"
    initial_admin_password: str = ""
    initial_agent_username: str = "agent"
    initial_agent_password: str = ""
    agent_latest_version: str = "0.2.0"
    agent_download_dir: str = "agent_downloads"
    agent_download_filename: str = "PrintBillingAgent.exe"
    agent_release_manifest_filename: str = "manifest.json"
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "no-reply@printbilling.local"
    smtp_use_tls: bool = True
    monthly_report_email_scheduler_enabled: bool = True
    monthly_report_email_scheduler_interval_seconds: int = Field(default=3600, ge=300, le=86400)

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

    @model_validator(mode="after")
    def validate_production_secrets(self):
        if self.environment.strip().lower() not in {"prod", "production"}:
            return self
        if self.secret_key == DEFAULT_SECRET_KEY:
            raise ValueError("SECRET_KEY proprio e obrigatorio em producao")
        if self.database_url.startswith("sqlite"):
            raise ValueError("DATABASE_URL deve usar banco servidor em producao")
        if self.database_url == DEFAULT_DATABASE_URL or DEFAULT_DATABASE_CREDENTIALS in self.database_url:
            raise ValueError("DATABASE_URL com credenciais proprias e obrigatorio em producao")
        if isinstance(self.cors_origins, list) and any(origin.strip() == "*" for origin in self.cors_origins):
            raise ValueError("CORS_ORIGINS nao pode usar wildcard em producao")
        return self

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
