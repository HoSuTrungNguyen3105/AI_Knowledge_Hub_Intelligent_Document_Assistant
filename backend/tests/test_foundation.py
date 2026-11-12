from pathlib import Path

import pytest
from conftest import TEST_SECRET
from pydantic import ValidationError

from app.core.config import Settings

BACKEND = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "secret",
    ["short", "x" * 64, "change-me-to-a-long-random-secret-12345", "replace-with-secret" * 3],
)
def test_unsafe_secret_rejected(secret):
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(_env_file=None, jwt_secret=secret)


def test_secret_required(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_load_root_env_and_json_origins(monkeypatch, tmp_path):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        f'JWT_SECRET={TEST_SECRET}\nCORS_ORIGINS=["https://app.example.com"]\nCOOKIE_SECURE=true\n',
        encoding="utf-8",
    )
    settings = Settings(_env_file=env_file)
    assert settings.cors_origins == ["https://app.example.com"]
    assert settings.cookie_secure is True
    assert settings.mongodb_uri.startswith("mongodb")


@pytest.mark.parametrize("origin", ["*", "null", "http://localhost:3000/", "https://*.example.com"])
def test_settings_reject_non_origin_allowlist(origin):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, jwt_secret=TEST_SECRET, cors_origins=[origin])


def test_mongodb_uri_validation():
    with pytest.raises(ValidationError, match="MONGODB_URI"):
        Settings(_env_file=None, jwt_secret=TEST_SECRET, mongodb_uri="postgresql://localhost/db")


def test_health_check(client):
    assert client.get("/api/v1/health").json() == {"status": "ok"}