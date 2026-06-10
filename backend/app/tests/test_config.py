import pytest
from pydantic import ValidationError

from app.core.config import DEFAULT_DATABASE_URL, DEFAULT_SECRET_KEY, Settings


PRODUCTION_DATABASE_URL = "postgresql+psycopg://billing_app:strong-db-password@db.example.com:5432/printbilling"


def test_production_rejects_default_secret_key():
    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            database_url=PRODUCTION_DATABASE_URL,
            secret_key=DEFAULT_SECRET_KEY,
            _env_file=None,
        )


def test_production_accepts_custom_secret_key():
    settings = Settings(
        environment="production",
        database_url=PRODUCTION_DATABASE_URL,
        secret_key="custom-production-secret-2026",
        _env_file=None,
    )

    assert settings.environment == "production"
    assert settings.secret_key == "custom-production-secret-2026"


def test_production_rejects_default_database_url():
    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            database_url=DEFAULT_DATABASE_URL,
            secret_key="custom-production-secret-2026",
            _env_file=None,
        )


def test_production_rejects_default_database_credentials_on_other_host():
    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            database_url="postgresql+psycopg://printbilling:printbilling@postgres:5432/printbilling",
            secret_key="custom-production-secret-2026",
            _env_file=None,
        )


def test_production_rejects_wildcard_cors_origins():
    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            database_url=PRODUCTION_DATABASE_URL,
            secret_key="custom-production-secret-2026",
            cors_origins="https://painel.example.com,*",
            _env_file=None,
        )


def test_production_accepts_explicit_cors_origins():
    settings = Settings(
        environment="production",
        database_url=PRODUCTION_DATABASE_URL,
        secret_key="custom-production-secret-2026",
        cors_origins="https://painel.example.com,https://admin.example.com",
        _env_file=None,
    )

    assert settings.cors_origins == ["https://painel.example.com", "https://admin.example.com"]


def test_development_allows_wildcard_cors_origins():
    settings = Settings(environment="development", cors_origins="*", _env_file=None)

    assert settings.cors_origins == ["*"]


def test_development_allows_default_secret_key():
    settings = Settings(environment="development", secret_key=DEFAULT_SECRET_KEY, _env_file=None)

    assert settings.secret_key == DEFAULT_SECRET_KEY
