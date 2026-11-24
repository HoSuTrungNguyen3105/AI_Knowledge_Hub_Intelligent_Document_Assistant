"""Offline contracts for in-app notifications (NEXORA Module 15, v1).

Covers the owner-scoped API (list/unread/mark-read/mark-all), the
best-effort ``notify`` helper other services emit through, and one real
emission path end to end: an AI Factory callback completing a run must
leave a notification for the run's owner.
"""

from uuid import UUID

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from test_compare import seed

from app.api.v1.n8n_factory import n8n_http
from app.services.notifications import notify

BASE = "/api/v1/ai/notifications"
FACTORY = "/api/v1/ai/n8n-factory"


@pytest.fixture(autouse=True)
def encryption(settings):
    settings.credential_encryption_key = SecretStr(Fernet.generate_key().decode())


@pytest.fixture
async def owner(client, register, db, settings):
    assert register(client).status_code == 201
    owner_id = UUID(client.get("/api/v1/auth/me").json()["id"])
    await seed(db, settings, owner_id)
    return client, owner_id, db


def test_notifications_require_auth(client):
    assert client.get(BASE).status_code == 401
    assert client.post(f"{BASE}/read-all").status_code == 401


async def test_empty_inbox(owner):
    client, _, _ = owner
    assert client.get(BASE).json() == {"notifications": [], "unread_count": 0}


async def test_notify_list_and_mark_read(owner):
    client, owner_id, db = owner
    await notify(db, owner_id, kind="workflow_completed", title="Xong A", body="b1")
    await notify(db, owner_id, kind="workflow_failed", title="Hỏng B", link="/agents/workflows")
    await notify(db, owner_id, kind="other", title="Không phải của người khác")
    other_id = UUID("12345678-1234-5678-1234-567812345678")
    await notify(db, other_id, kind="other", title="Của người khác")

    body = client.get(BASE).json()
    assert body["unread_count"] == 3
    titles = [n["title"] for n in body["notifications"]]
    assert titles[0] == "Không phải của người khác"  # newest first
    assert "Của người khác" not in titles

    first = body["notifications"][0]
    read = client.post(f"{BASE}/{first['id']}/read")
    assert read.status_code == 200
    assert read.json()["read_at"] is not None
    assert client.get(BASE).json()["unread_count"] == 2

    rest = client.post(f"{BASE}/read-all")
    assert rest.status_code == 200
    assert rest.json()["unread_count"] == 0
    assert all(n["read_at"] is not None for n in rest.json()["notifications"])


async def test_mark_read_is_owner_scoped(owner, client_factory, register, db, settings):
    client, owner_id, _ = owner
    await notify(db, owner_id, kind="k", title="Riêng tư")
    mine = client.get(BASE).json()["notifications"][0]

    stranger = client_factory()
    assert register(stranger, email="stranger@example.com").status_code == 201
    response = stranger.post(f"{BASE}/{mine['id']}/read")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "notification_not_found"
    assert stranger.get(BASE).json() == {"notifications": [], "unread_count": 0}


class FakeN8n:
    def __init__(self):
        self.calls = []

    async def post_json(self, url, payload, timeout_seconds):
        self.calls.append({"url": url, "payload": payload})
        return {"accepted": True, "run_id": payload.get("run_id")}


@pytest.fixture
def fake_n8n(app):
    fake = FakeN8n()
    app.dependency_overrides[n8n_http] = lambda: fake
    return fake


async def test_factory_completion_emits_notification(owner, fake_n8n, client_factory):
    client, _, _ = owner
    created = client.post(
        f"{FACTORY}/runs", json={"requirement": "Làm web", "domain": ["software"]}
    )
    assert created.status_code == 202, created.text
    run = created.json()
    token = fake_n8n.calls[0]["payload"]["callback_token"]

    anon = client_factory()
    done = anon.post(
        f"{FACTORY}/runs/{run['id']}/callback",
        json={"package": {"status": "completed", "final": {"summary": "OK"}}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert done.status_code == 200, done.text

    inbox = client.get(BASE).json()
    assert inbox["unread_count"] == 1
    note = inbox["notifications"][0]
    assert note["kind"] == "factory_completed"
    assert note["link"] == "/agents/workflows?tab=factory"

    # A duplicate callback must not emit a second notification.
    again = anon.post(
        f"{FACTORY}/runs/{run['id']}/callback",
        json={"package": {"status": "completed"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert again.status_code == 200
    assert client.get(BASE).json()["unread_count"] == 1
