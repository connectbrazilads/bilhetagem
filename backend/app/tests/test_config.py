import pytest
from pydantic import ValidationError

from app.core.config import DEFAULT_SECRET_KEY, Settings


def test_production_rejects_default_secret_key():
    with pytest.raises(ValidationError):
        Settings(environment="production", secret_key=DEFAULT_SECRET_KEY, _env_file=None)


def test_production_accepts_custom_secret_key():
    settings = Settings(environment="production", secret_key="custom-production-secret-2026", _env_file=None)

    assert settings.environment == "production"
    assert settings.secret_key == "custom-production-secret-2026"


def test_production_rejects_wildcard_cors_origins():
    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            secret_key="custom-production-secret-2026",
            cors_origins="https://painel.example.com,*",
            _env_file=None,
        )


def test_production_accepts_explicit_cors_origins():
    settings = Settings(
        environment="production",
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
