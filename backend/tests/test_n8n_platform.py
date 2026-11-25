"""Offline contracts for the n8n Platform management bridge (phase 1).

The n8n REST client is replaced with a fake: no network, no real n8n.
These tests verify the management contract — status reporting never fails
on an unconfigured instance, the workflow list is mirrored and mapped to
the platform shape, and activation goes to the n8n REST API — not a live
n8n run.
"""

import pytest
from pydantic import SecretStr

from app.api.v1.n8n_platform import n8n_api_http
from app.services.n8n_platform import parse_workflow

BASE = "/api/v1/ai/n8n-platform"

WORKFLOW_07 = {
    "id": "wf07abc",
    "name": "07 - Seven Agent Dynamic Routing",
    "active": True,
    "tags": [{"id": "t1", "name": "factory"}],
    "nodes": [
        {
            "type": "n8n-nodes-base.webhook",
            "parameters": {"path": "ai-team/start"},
        },
        {"type": "n8n-nodes-base.code", "parameters": {}},
        {"type": "n8n-nodes-base.httpRequest", "parameters": {}},
    ],
    "createdAt": "2026-11-24T00:00:00.000Z",
    "updatedAt": "2026-11-24T01:00:00.000Z",
}

WORKFLOW_08 = {
    "id": "wf08def",
    "name": "08 - Scheduled Research Digest",
    "active": False,
    "tags": [],
    "nodes": [{"type": "n8n-nodes-base.scheduleTrigger", "parameters": {}}],
    "createdAt": "2026-11-24T00:00:00.000Z",
    "updatedAt": "2026-11-24T00:30:00.000Z",
}


class FakeN8nApi:
    """Stands in for the n8n public REST API."""

    def __init__(self, workflows=None, status=200):
        self.workflows = workflows if workflows is not None else [WORKFLOW_07, WORKFLOW_08]
        self.status = status
        self.gets = []
        self.posts = []
        self.patches = []
        self.deletes = []

    execution_mode = "error"

    async def get_json(self, url, api_key, timeout_seconds):
        self.gets.append({"url": url, "api_key": api_key})
        if self.status != 200:
            return self.status, {"message": "nope"}
        if "/executions" in url:
            from datetime import datetime, timezone

            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            if "/executions/" in url:
                if self.execution_mode == "running":
                    return 200, {
                        "id": "e123",
                        "workflowId": "wf07abc",
                        "status": "running",
                        "finished": False,
                        "startedAt": now,
                        "data": {
                            "resultData": {
                                "runData": {
                                    "Team Webhook": [{"executionTime": 5}],
                                }
                            }
                        },
                    }
                return 200, {
                    "id": "e123",
                    "workflowId": "wf07abc",
                    "status": "error",
                    "finished": True,
                    "startedAt": now,
                    "stoppedAt": now,
                    "data": {
                        "resultData": {
                            "runData": {
                                "Team Webhook": [{"executionTime": 5}],
                                "Code": [
                                    {"executionTime": 30, "error": {"message": "boom"}}
                                ],
                            },
                            "error": {"message": "boom"},
                        }
                    },
                }
            return 200, {
                "data": [
                    {"id": "e123", "workflowId": "wf07abc", "startedAt": now, "status": "error"}
                ],
                "nextCursor": None,
            }
        if "/workflows/" in url and "limit" not in url:
            workflow_id = url.rsplit("/workflows/", 1)[1]
            for raw in self.workflows:
                if raw["id"] == workflow_id:
                    import copy

                    return 200, copy.deepcopy(raw)
            return 404, {"message": "not found"}
        if "limit=1" in url:
            return 200, {"data": self.workflows[:1], "nextCursor": None}
        return 200, {"data": list(self.workflows), "nextCursor": None}

    async def post_json_body(self, url, api_key, payload, timeout_seconds):
        self.posts.append({"url": url, "api_key": api_key, "payload": payload})
        if self.status != 200:
            return self.status, {"message": "nope"}
        if "/webhook/" in url:
            return 200, {"ok": True}
        return 201, {**payload, "id": "newid123", "active": False, "tags": []}

    async def delete_json(self, url, api_key, timeout_seconds):
        self.deletes.append({"url": url, "api_key": api_key})
        return 204

    async def patch_json(self, url, api_key, payload, timeout_seconds):
        self.patches.append({"url": url, "api_key": api_key, "payload": payload})
        if self.status != 200:
            return self.status, {"message": "nope"}
        workflow_id = url.rsplit("/workflows/", 1)[1]
        return 200, {**payload, "id": workflow_id, "active": True, "tags": []}

    async def post_json(self, url, api_key, timeout_seconds):
        self.posts.append({"url": url, "api_key": api_key})
        if self.status != 200:
            return self.status, {"message": "nope"}
        workflow_id = url.split("/workflows/")[1].split("/")[0]
        for raw in self.workflows:
            if raw["id"] == workflow_id:
                updated = {**raw, "active": url.endswith("/activate")}
                return 200, updated
        return 404, {"message": "not found"}


@pytest.fixture
async def owner(client, register):
    assert register(client).status_code == 201
    return client


@pytest.fixture
def fake_api(app, settings):
    settings.n8n_api_key = SecretStr("test-n8n-key")
    fake = FakeN8nApi()
    app.dependency_overrides[n8n_api_http] = lambda: fake
    return fake


def test_platform_requires_auth(client):
    assert client.get(f"{BASE}/status").status_code == 401
    assert client.get(f"{BASE}/workflows").status_code == 401
    assert client.post(f"{BASE}/workflows/wf07abc/activate").status_code == 401


async def test_status_not_configured(owner, app, settings):
    settings.n8n_api_key = None
    fake = FakeN8nApi()
    app.dependency_overrides[n8n_api_http] = lambda: fake
    response = owner.get(f"{BASE}/status")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["configured"] is False
    assert body["authenticated"] is False
    assert body["error"] == "n8n_api_not_configured"
    # No key, no upstream call at all.
    assert fake.gets == []


async def test_status_ok(owner, fake_api):
    response = owner.get(f"{BASE}/status")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["configured"] is True
    assert body["reachable"] is True
    assert body["authenticated"] is True
    assert body["error"] is None
    assert fake_api.gets[0]["api_key"] == "test-n8n-key"
    assert "/api/v1/workflows" in fake_api.gets[0]["url"]


async def test_status_unauthorized_key(owner, app, settings):
    settings.n8n_api_key = SecretStr("wrong-key")
    app.dependency_overrides[n8n_api_http] = lambda: FakeN8nApi(status=401)
    response = owner.get(f"{BASE}/status")
    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert body["reachable"] is True
    assert body["authenticated"] is False
    assert body["error"] == "n8n_api_unauthorized"


async def test_list_workflows_syncs_and_maps(owner, fake_api):
    response = owner.get(f"{BASE}/workflows")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2
    assert body["sync_error"] is None
    assert body["synced_at"] is not None
    by_id = {item["id"]: item for item in body["items"]}
    wf07 = by_id["wf07abc"]
    assert wf07["active"] is True
    assert wf07["tags"] == ["factory"]
    assert wf07["triggers"] == ["webhook"]
    assert wf07["webhook_paths"] == ["ai-team/start"]
    assert wf07["node_count"] == 3
    assert wf07["editor_url"].endswith("/workflow/wf07abc")
    assert by_id["wf08def"]["triggers"] == ["schedule"]


async def test_list_workflows_unconfigured_returns_empty(owner, settings):
    settings.n8n_api_key = None
    response = owner.get(f"{BASE}/workflows")
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["sync_error"] == "n8n_api_not_configured"


async def test_activate_and_deactivate(owner, fake_api):
    activated = owner.post(f"{BASE}/workflows/wf08def/activate")
    assert activated.status_code == 200, activated.text
    assert activated.json()["active"] is True
    assert fake_api.posts[0]["url"].endswith("/api/v1/workflows/wf08def/activate")

    deactivated = owner.post(f"{BASE}/workflows/wf07abc/deactivate")
    assert deactivated.status_code == 200
    assert deactivated.json()["active"] is False
    assert fake_api.posts[1]["url"].endswith("/api/v1/workflows/wf07abc/deactivate")


async def test_activate_unknown_workflow_is_404(owner, fake_api):
    response = owner.post(f"{BASE}/workflows/nope/activate")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "n8n_workflow_not_found"


async def test_activate_unconfigured_is_503(owner, settings):
    settings.n8n_api_key = None
    response = owner.post(f"{BASE}/workflows/wf07abc/activate")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "n8n_api_not_configured"


async def test_workflow_detail_lists_scalar_params(owner, fake_api):
    response = owner.get(f"{BASE}/workflows/wf07abc")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == WORKFLOW_07["name"]
    assert len(body["nodes"]) == 3
    webhook_node = body["nodes"][0]
    params = {p["path"]: p for p in webhook_node["parameters"]}
    assert params["path"] == {"path": "path", "value": "ai-team/start", "kind": "string"}


async def test_update_parameters_changes_value(owner, fake_api):
    fake_api.workflows = [
        {
            **WORKFLOW_07,
            "nodes": [
                {
                    "name": "Start",
                    "type": "n8n-nodes-base.webhook",
                    "parameters": {"path": "ai-team/start", "options": {"timeout": 30}},
                }
            ],
        }
    ]
    response = owner.post(
        f"{BASE}/workflows/wf07abc/parameters",
        json={"updates": [{"node": "Start", "path": "options.timeout", "value": 60}]},
    )
    assert response.status_code == 200, response.text
    assert len(fake_api.patches) == 1
    patch = fake_api.patches[0]
    assert patch["url"].endswith("/api/v1/workflows/wf07abc")
    sent_node = patch["payload"]["nodes"][0]
    assert sent_node["parameters"]["options"]["timeout"] == 60
    assert sent_node["parameters"]["path"] == "ai-team/start"
    params = {p["path"]: p["value"] for p in response.json()["nodes"][0]["parameters"]}
    assert params["options.timeout"] == 60


async def test_update_parameters_rejects_unknown_and_type_mismatch(owner, fake_api):
    fake_api.workflows = [
        {
            **WORKFLOW_07,
            "nodes": [
                {
                    "name": "Start",
                    "type": "n8n-nodes-base.webhook",
                    "parameters": {"path": "ai-team/start"},
                }
            ],
        }
    ]
    unknown = owner.post(
        f"{BASE}/workflows/wf07abc/parameters",
        json={"updates": [{"node": "Start", "path": "missing", "value": "x"}]},
    )
    assert unknown.status_code == 422
    assert unknown.json()["detail"]["code"] == "n8n_parameter_not_found"
    mismatch = owner.post(
        f"{BASE}/workflows/wf07abc/parameters",
        json={"updates": [{"node": "Start", "path": "path", "value": 42}]},
    )
    assert mismatch.status_code == 422
    # Nothing was PATCHed for rejected updates.
    assert fake_api.patches == []


async def test_workflow_detail_unknown_is_404(owner, fake_api):
    response = owner.get(f"{BASE}/workflows/nope")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "n8n_workflow_not_found"


CREATE_BODY = {
    "name": "My new workflow",
    "nodes": [
        {
            "name": "Start",
            "type": "n8n-nodes-base.webhook",
            "parameters": {"path": "my-hook"},
        }
    ],
    "connections": {},
}


async def test_create_workflow(owner, fake_api):
    response = owner.post(f"{BASE}/workflows", json=CREATE_BODY)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"] == "newid123"
    assert body["name"] == "My new workflow"
    assert body["active"] is False
    assert body["triggers"] == ["webhook"]
    assert len(fake_api.posts) == 1
    assert fake_api.posts[0]["url"].endswith("/api/v1/workflows")
    assert fake_api.posts[0]["payload"]["nodes"][0]["name"] == "Start"


async def test_create_workflow_rejects_nameless_node(owner, fake_api):
    bad = {**CREATE_BODY, "nodes": [{"type": "n8n-nodes-base.code", "parameters": {}}]}
    response = owner.post(f"{BASE}/workflows", json=bad)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "n8n_workflow_invalid"
    assert fake_api.posts == []


async def test_create_workflow_unconfigured_is_503(owner, settings):
    settings.n8n_api_key = None
    response = owner.post(f"{BASE}/workflows", json=CREATE_BODY)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "n8n_api_not_configured"


async def _sync(owner):
    response = owner.get(f"{BASE}/workflows")
    assert response.status_code == 200, response.text


async def test_start_run_reconciles_execution(owner, fake_api):
    await _sync(owner)
    response = owner.post(
        f"{BASE}/runs", json={"workflow_id": "wf07abc", "payload": {"topic": "x"}}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "error"
    assert body["error"] == "boom"
    assert body["n8n_execution_id"] == "e123"
    nodes = {item["name"]: item for item in body["node_statuses"]}
    assert nodes["Team Webhook"]["status"] == "success"
    assert nodes["Code"]["status"] == "error"
    assert nodes["Code"]["error"] == "boom"
    webhook_calls = [p for p in fake_api.posts if "/webhook/ai-team/start" in p["url"]]
    assert len(webhook_calls) == 1
    assert webhook_calls[0]["payload"] == {"topic": "x"}
    assert webhook_calls[0]["api_key"] == ""


async def test_start_run_inactive_rejected(owner, fake_api):
    await _sync(owner)
    response = owner.post(f"{BASE}/runs", json={"workflow_id": "wf08def", "payload": {}})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "n8n_workflow_inactive"


async def test_start_run_unknown_workflow(owner, fake_api):
    response = owner.post(f"{BASE}/runs", json={"workflow_id": "nope", "payload": {}})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "n8n_workflow_not_found"


async def test_stop_running_run(owner, fake_api):
    fake_api.execution_mode = "running"
    await _sync(owner)
    created = owner.post(f"{BASE}/runs", json={"workflow_id": "wf07abc", "payload": {}})
    assert created.status_code == 201, created.text
    run = created.json()
    assert run["status"] == "running"
    assert run["n8n_execution_id"] == "e123"
    stopped = owner.post(f"{BASE}/runs/{run['id']}/stop")
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["status"] == "stopped"
    assert any("/executions/e123" in d["url"] for d in fake_api.deletes)


async def test_retry_run(owner, fake_api):
    await _sync(owner)
    created = owner.post(f"{BASE}/runs", json={"workflow_id": "wf07abc", "payload": {"a": 1}})
    run = created.json()
    retried = owner.post(f"{BASE}/runs/{run['id']}/retry")
    assert retried.status_code == 201, retried.text
    body = retried.json()
    assert body["id"] != run["id"]
    assert body["retry_of"] == run["id"]
    assert body["input"] == {"a": 1}


async def test_list_runs(owner, fake_api):
    await _sync(owner)
    owner.post(f"{BASE}/runs", json={"workflow_id": "wf07abc", "payload": {}})
    response = owner.get(f"{BASE}/runs")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["workflow_id"] == "wf07abc"


def test_parse_workflow_shape():
    item = parse_workflow(WORKFLOW_07, "http://localhost:5678")
    assert item.id == "wf07abc"
    assert item.triggers == ["webhook"]
    assert item.webhook_paths == ["ai-team/start"]
    assert item.editor_url == "http://localhost:5678/workflow/wf07abc"
