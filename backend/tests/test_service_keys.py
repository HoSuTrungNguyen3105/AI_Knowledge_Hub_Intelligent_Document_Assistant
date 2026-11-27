"""Offline contracts for the service key vault + push-to-n8n.

The n8n REST client is replaced with a fake (same override point as the
n8n platform tests): no network, no real n8n, no real secrets — every
value below is a generated fixture string.
"""

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from app.api.v1.n8n_platform import n8n_api_http

BASE = "/api/v1/ai/service-keys"

ZALO_FIELDS = {
    "app_id": "1234567890123456789",
    "secret_key": "zalo-secret-key-123",
    "access_token": "zalo-access-token-abc123",
    "refresh_token": "zalo-refresh-token-xyz789",
}
TELEGRAM_FIELDS = {"bot_token": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"}


class FakeN8nCredentialsApi:
    """Stands in for the n8n public REST API (credentials endpoints)."""

    def __init__(self, put_status=200):
        self.put_status = put_status
        self.posts = []
        self.puts = []
        self._seq = 0

    async def post_json_body(self, url, api_key, payload, timeout_seconds):
        self.posts.append({"url": url, "api_key": api_key, "payload": payload})
        if "/credentials" not in url:
            return 404, {"message": "not found"}
        self._seq += 1
        return 201, {**payload, "id": f"cred-{self._seq}"}

    async def put_json(self, url, api_key, payload, timeout_seconds):
        self.puts.append({"url": url, "api_key": api_key, "payload": payload})
        if self.put_status != 200:
            return self.put_status, {"message": "nope"}
        return 200, {**payload, "id": url.rsplit("/", 1)[1]}


@pytest.fixture
async def owner(client, register):
    assert register(client).status_code == 201
    return client


@pytest.fixture
def fake_n8n(app, settings):
    settings.credential_encryption_key = SecretStr(Fernet.generate_key().decode())
    settings.n8n_api_key = SecretStr("test-n8n-key")
    fake = FakeN8nCredentialsApi()
    app.dependency_overrides[n8n_api_http] = lambda: fake
    return fake


def _create_zalo(owner, **overrides):
    payload = {"name": "Zalo OA chính", "service": "zalo_oa", "fields": dict(ZALO_FIELDS)}
    payload.update(overrides)
    response = owner.post(BASE, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_service_keys_require_auth(client):
    assert client.get(BASE).status_code == 401
    assert client.get(f"{BASE}/presets").status_code == 401
    assert client.post(BASE, json={}).status_code == 401


def test_presets_cover_three_services(owner, fake_n8n):
    response = owner.get(f"{BASE}/presets")
    assert response.status_code == 200, response.text
    by_service = {item["service"]: item for item in response.json()["items"]}
    assert set(by_service) == {"zalo_oa", "telegram_bot", "http_header"}
    zalo = by_service["zalo_oa"]
    assert zalo["n8n_credential_type"] == "httpHeaderAuth"
    assert [f["key"] for f in zalo["fields"]] == [
        "app_id",
        "secret_key",
        "access_token",
        "refresh_token",
    ]
    assert by_service["telegram_bot"]["n8n_credential_type"] == "telegramApi"


async def test_create_encrypts_and_never_returns_values(owner, fake_n8n, db):
    body = _create_zalo(owner)
    assert body["credential_name"] == "MindFlow — Zalo OA chính"
    assert body["n8n_credential_id"] is None
    assert body["last_pushed_at"] is None
    flags = {field["key"]: field["has_value"] for field in body["fields"]}
    assert flags == {key: True for key in ZALO_FIELDS}
    # No submitted value appears anywhere in the response…
    for value in ZALO_FIELDS.values():
        assert value not in str(body)
    # …nor in the stored document (everything is ciphertext).
    doc = await db["service_keys"].find_one({"_id": body["id"]})
    assert doc is not None
    for value in ZALO_FIELDS.values():
        assert value not in str(doc)
    assert set(doc["fields"]) == set(ZALO_FIELDS)


def test_create_rejects_missing_required_and_bad_values(owner, fake_n8n):
    missing = owner.post(
        BASE,
        json={"name": "Thiếu", "service": "zalo_oa", "fields": {"app_id": "123456789"}},
    )
    assert missing.status_code == 422
    assert "service_key_invalid" in missing.text

    unknown = owner.post(
        BASE,
        json={
            "name": "Lạ",
            "service": "zalo_oa",
            "fields": {**ZALO_FIELDS, "bogus": "whatever-123"},
        },
    )
    assert unknown.status_code == 422
    assert "service_key_invalid" in unknown.text

    spaced = owner.post(
        BASE,
        json={
            "name": "Có dấu cách",
            "service": "telegram_bot",
            "fields": {"bot_token": "token with spaces 123"},
        },
    )
    assert spaced.status_code == 422
    assert "service_key_invalid" in spaced.text


def test_push_creates_then_updates_credential(owner, fake_n8n):
    entry = _create_zalo(owner)

    pushed = owner.post(f"{BASE}/{entry['id']}/push")
    assert pushed.status_code == 200, pushed.text
    body = pushed.json()
    assert body["n8n_credential_id"] == "cred-1"
    assert body["n8n_credential_type"] == "httpHeaderAuth"
    assert len(fake_n8n.posts) == 1
    post = fake_n8n.posts[0]
    assert post["url"].endswith("/api/v1/credentials")
    assert post["api_key"] == "test-n8n-key"
    assert post["payload"]["name"] == "MindFlow — Zalo OA chính"
    assert post["payload"]["type"] == "httpHeaderAuth"
    assert post["payload"]["data"] == {
        "name": "access_token",
        "value": ZALO_FIELDS["access_token"],
    }

    # Second push updates the SAME credential (no duplicate in n8n),
    # and the update body carries no immutable "type".
    pushed2 = owner.post(f"{BASE}/{entry['id']}/push")
    assert pushed2.status_code == 200, pushed2.text
    assert pushed2.json()["n8n_credential_id"] == "cred-1"
    assert len(fake_n8n.posts) == 1
    assert len(fake_n8n.puts) == 1
    put = fake_n8n.puts[0]
    assert put["url"].endswith("/api/v1/credentials/cred-1")
    assert "type" not in put["payload"]
    assert put["payload"]["data"]["value"] == ZALO_FIELDS["access_token"]

    listed = owner.get(BASE).json()
    assert listed["total"] == 1
    assert listed["items"][0]["n8n_credential_id"] == "cred-1"
    assert listed["items"][0]["last_pushed_at"] is not None


def test_push_recreates_when_credential_deleted_in_n8n(owner, app, settings):
    settings.credential_encryption_key = SecretStr(Fernet.generate_key().decode())
    settings.n8n_api_key = SecretStr("test-n8n-key")
    fake = FakeN8nCredentialsApi()
    app.dependency_overrides[n8n_api_http] = lambda: fake
    entry = _create_zalo(owner)
    assert owner.post(f"{BASE}/{entry['id']}/push").status_code == 200

    fake.put_status = 404
    pushed = owner.post(f"{BASE}/{entry['id']}/push")
    assert pushed.status_code == 200, pushed.text
    assert pushed.json()["n8n_credential_id"] == "cred-2"
    assert len(fake.posts) == 2


def test_push_telegram_payload(owner, fake_n8n):
    created = owner.post(
        BASE,
        json={"name": "Bot thông báo", "service": "telegram_bot", "fields": dict(TELEGRAM_FIELDS)},
    )
    assert created.status_code == 201, created.text
    pushed = owner.post(f"{BASE}/{created.json()['id']}/push")
    assert pushed.status_code == 200, pushed.text
    payload = fake_n8n.posts[0]["payload"]
    assert payload["type"] == "telegramApi"
    assert payload["data"] == {"accessToken": TELEGRAM_FIELDS["bot_token"]}


def test_push_fails_without_the_pushed_value(owner, fake_n8n):
    created = owner.post(
        BASE,
        json={
            "name": "Zalo chưa có token",
            "service": "zalo_oa",
            "fields": {"app_id": ZALO_FIELDS["app_id"], "secret_key": ZALO_FIELDS["secret_key"]},
        },
    )
    assert created.status_code == 201, created.text
    pushed = owner.post(f"{BASE}/{created.json()['id']}/push")
    assert pushed.status_code == 422
    assert "service_key_invalid" in pushed.text
    assert fake_n8n.posts == []


def test_push_fails_when_n8n_not_configured(owner, app, settings):
    settings.credential_encryption_key = SecretStr(Fernet.generate_key().decode())
    settings.n8n_api_key = None
    fake = FakeN8nCredentialsApi()
    app.dependency_overrides[n8n_api_http] = lambda: fake
    entry = _create_zalo(owner)
    pushed = owner.post(f"{BASE}/{entry['id']}/push")
    assert pushed.status_code == 503
    assert "n8n_api_not_configured" in pushed.text
    assert fake.posts == []


def test_update_rotates_and_clears_values(owner, fake_n8n):
    entry = _create_zalo(owner)
    rotated = owner.patch(
        f"{BASE}/{entry['id']}",
        json={"fields": {"access_token": "zalo-access-token-NEW999"}},
    )
    assert rotated.status_code == 200, rotated.text
    assert owner.post(f"{BASE}/{entry['id']}/push").status_code == 200
    assert fake_n8n.posts[0]["payload"]["data"]["value"] == "zalo-access-token-NEW999"

    cleared = owner.patch(
        f"{BASE}/{entry['id']}", json={"fields": {"access_token": ""}}
    )
    assert cleared.status_code == 200, cleared.text
    flags = {f["key"]: f["has_value"] for f in cleared.json()["fields"]}
    assert flags["access_token"] is False
    assert flags["secret_key"] is True
    pushed = owner.post(f"{BASE}/{entry['id']}/push")
    assert pushed.status_code == 422


def test_delete_and_missing_entry(owner, fake_n8n):
    entry = _create_zalo(owner)
    assert owner.delete(f"{BASE}/{entry['id']}").status_code == 204
    assert owner.get(BASE).json()["total"] == 0
    assert owner.delete(f"{BASE}/{entry['id']}").status_code == 404
    missing = owner.post(f"{BASE}/00000000-0000-0000-0000-000000000000/push")
    assert missing.status_code == 404
    assert "service_key_not_found" in missing.text
