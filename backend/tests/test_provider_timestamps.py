"""The stored key's created_at / updated_at are exposed on the provider
metadata and on the models endpoint, so the user can tell which key was
saved or changed most recently. Offline contract tests, fixture keys only.
"""

from datetime import datetime

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

BASE = "/api/v1/ai/providers"
KEY = "contract-only-api-key"
KEY2 = "contract-only-api-key-2"


@pytest.fixture(autouse=True)
def provider_settings(settings):
    settings.credential_encryption_key = SecretStr(Fernet.generate_key().decode())
    return settings


@pytest.fixture
def owner(client, register):
    assert register(client).status_code == 201
    return client


def _parse(value):
    assert value, "timestamp missing"
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _metadata(client, slug="openai"):
    providers = client.get(BASE).json()["providers"]
    return next(p for p in providers if p["id"] == slug)


def test_timestamps_absent_until_key_saved(owner):
    meta = _metadata(owner)
    assert meta["created_at"] is None
    assert meta["updated_at"] is None
    models = owner.get(f"{BASE}/openai/models").json()
    assert models["created_at"] is None
    assert models["updated_at"] is None


def test_save_sets_created_and_updated_and_models_endpoint_carries_them(owner):
    saved = owner.patch(f"{BASE}/openai", json={"api_key": KEY})
    assert saved.status_code == 200, saved.text
    body = saved.json()
    created = _parse(body["created_at"])
    updated = _parse(body["updated_at"])
    assert created == updated

    meta = _metadata(owner)
    assert meta["created_at"] == body["created_at"]
    assert meta["updated_at"] == body["updated_at"]

    models = owner.get(f"{BASE}/openai/models").json()
    assert models["created_at"] == body["created_at"]
    assert models["updated_at"] == body["updated_at"]


def test_update_keeps_created_and_moves_updated(owner):
    first = owner.patch(f"{BASE}/openai", json={"api_key": KEY}).json()
    toggled = owner.patch(f"{BASE}/openai", json={"enabled": False})
    assert toggled.status_code == 200, toggled.text
    body = toggled.json()
    assert body["created_at"] == first["created_at"]
    assert _parse(body["updated_at"]) >= _parse(first["updated_at"])

    rotated = owner.patch(f"{BASE}/openai", json={"api_key": KEY2})
    assert rotated.status_code == 200, rotated.text
    assert rotated.json()["created_at"] == first["created_at"]
    assert _parse(rotated.json()["updated_at"]) >= _parse(body["updated_at"])
