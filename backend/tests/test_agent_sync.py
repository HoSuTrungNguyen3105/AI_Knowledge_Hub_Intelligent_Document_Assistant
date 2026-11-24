"""Offline contracts for the agent.created n8n webhook
(mindflow-workforce-feature section 11, wave 5).

Creating an AI workforce resource POSTs the contract payload to the
configured n8n webhook (never any API key) and stores the delivery
state on the resource: synced only when n8n answers 200 with
received=true and the matching agentId; failed after 3 attempts;
pending when no webhook URL is configured. Humans never sync, and a
manual re-sync is available per resource.
"""

import json

import httpx
import pytest

from app.api.v1.resources import webhook_transport

RESOURCES = "/api/v1/ai/resources"

AI_PAYLOAD = {
    "type": "ai",
    "name": "AI Developer",
    "role": "Coding Agent",
    "skills": [{"name": "Python", "level": 5}],
    "availability_status": "connected",
    "ai": {
        "provider": "groq",
        "model": "openai/gpt-oss-120b",
        "denied_scopes": ["payment-data"],
        "token_limit_per_task": 20000,
    },
}

HUMAN_PAYLOAD = {
    "type": "human",
    "name": "Nguyễn Văn A",
    "role": "Developer",
    "skills": [{"name": "Python", "level": 4}],
    "human": {"experience_years": 3, "hours_per_week": 40, "current_project_count": 0},
}


@pytest.fixture
def owner(client, register):
    assert register(client).status_code == 201
    return client


@pytest.fixture
def webhook(app, settings):
    settings.n8n_agent_webhook_url = "http://n8n.test/webhook/mindflow-agent-created"
    settings.n8n_agent_webhook_secret = "test-secret"
    box = {"mode": "ok", "requests": []}

    def handler(request):
        body = json.loads(request.content)
        box["requests"].append({"headers": dict(request.headers), "body": body})
        if box["mode"] == "ok":
            return httpx.Response(200, json={
                "received": True,
                "agentId": body["agent"]["id"],
                "event": body["event"],
                "executionId": "exec-1",
                "receivedAt": "2026-01-01T00:00:00Z",
            })
        if box["mode"] == "bad-receipt":
            return httpx.Response(200, json={"received": False})
        return httpx.Response(500, json={"error": "boom"})

    app.dependency_overrides[webhook_transport] = lambda: httpx.MockTransport(handler)
    return box


def test_ai_create_syncs_to_n8n(owner, webhook):
    response = owner.post(RESOURCES, json=AI_PAYLOAD)
    assert response.status_code == 201, response.text
    resource = response.json()
    assert resource["n8n_sync"]["status"] == "synced"
    assert resource["n8n_sync"]["execution_id"] == "exec-1"

    assert len(webhook["requests"]) == 1
    sent = webhook["requests"][0]
    assert sent["headers"]["x-mindflow-secret"] == "test-secret"
    body = sent["body"]
    assert body["event"] == "agent.created"
    agent = body["agent"]
    assert agent["id"] == resource["id"]
    assert agent["provider"] == "groq"
    assert agent["deniedScopes"] == ["payment-data"]
    assert agent["tokenLimitPerTask"] == 20000
    assert agent["skills"] == ["Python"]
    assert agent["status"] == "active"
    assert "api_key" not in json.dumps(body).lower()
    assert "apiKey" not in body["agent"]


def test_human_create_never_syncs(owner, webhook):
    response = owner.post(RESOURCES, json=HUMAN_PAYLOAD)
    assert response.status_code == 201
    assert response.json()["n8n_sync"] is None
    assert webhook["requests"] == []


def test_unconfigured_webhook_stays_pending(owner):
    response = owner.post(RESOURCES, json=AI_PAYLOAD)
    assert response.status_code == 201
    sync = response.json()["n8n_sync"]
    assert sync["status"] == "pending"
    assert sync["error"] == "webhook_not_configured"


def test_failed_delivery_after_retries(owner, webhook):
    webhook["mode"] = "fail"
    response = owner.post(RESOURCES, json=AI_PAYLOAD)
    assert response.status_code == 201
    sync = response.json()["n8n_sync"]
    assert sync["status"] == "failed"
    assert sync["error"] == "http_500"
    assert len(webhook["requests"]) == 3


def test_bad_receipt_is_a_failure(owner, webhook):
    webhook["mode"] = "bad-receipt"
    response = owner.post(RESOURCES, json=AI_PAYLOAD)
    sync = response.json()["n8n_sync"]
    assert sync["status"] == "failed"
    assert sync["error"] == "unexpected_receipt"


def test_manual_resync(owner, webhook):
    webhook["mode"] = "fail"
    created = owner.post(RESOURCES, json=AI_PAYLOAD).json()
    assert created["n8n_sync"]["status"] == "failed"

    webhook["mode"] = "ok"
    response = owner.post(f"{RESOURCES}/{created['id']}/sync-n8n")
    assert response.status_code == 200, response.text
    assert response.json()["n8n_sync"]["status"] == "synced"

    human = owner.post(RESOURCES, json=HUMAN_PAYLOAD).json()
    response = owner.post(f"{RESOURCES}/{human['id']}/sync-n8n")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "resource_not_ai"
