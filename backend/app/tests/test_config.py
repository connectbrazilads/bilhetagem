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


def test_production_rejects_sqlite_database_url():
    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            database_url="sqlite:///printbilling.db",
            secret_key="custom-production-secret-2026",
            _env_file=None,
        )


def test_development_allows_sqlite_database_url():
    settings = Settings(database_url="sqlite:///printbilling.db", _env_file=None)

    assert settings.database_url == "sqlite:///printbilling.db"


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


def test_accepts_supported_jwt_algorithm():
    settings = Settings(algorithm="HS512", _env_file=None)

    assert settings.algorithm == "HS512"


@pytest.mark.parametrize("algorithm", ["none", "RS256"])
def test_rejects_unsupported_jwt_algorithm(algorithm: str):
    with pytest.raises(ValidationError):
        Settings(algorithm=algorithm, _env_file=None)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("access_token_expire_minutes", 0),
        ("default_monthly_quota", -1),
        ("snmp_timeout_seconds", 0),
        ("snmp_retries", -1),
        ("smtp_port", 0),
        ("monthly_report_email_scheduler_interval_seconds", 299),
    ],
)
def test_rejects_invalid_operational_numeric_settings(field: str, value):
    with pytest.raises(ValidationError):
        Settings(**{field: value}, _env_file=None)


def test_accepts_boundary_operational_numeric_settings():
    settings = Settings(
        access_token_expire_minutes=5,
        default_monthly_quota=0,
        snmp_timeout_seconds=0.1,
        snmp_retries=0,
        smtp_port=1,
        monthly_report_email_scheduler_interval_seconds=300,
        _env_file=None,
    )

    assert settings.access_token_expire_minutes == 5
    assert settings.default_monthly_quota == 0
    assert settings.snmp_timeout_seconds == 0.1
    assert settings.snmp_retries == 0
    assert settings.smtp_port == 1
    assert settings.monthly_report_email_scheduler_interval_seconds == 300
