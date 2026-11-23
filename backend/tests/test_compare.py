"""Authenticated compare API contract tests over the offline MongoDB mock.

Generation is intercepted by httpx.MockTransport; nothing here proves a live
provider call. These verify parallel runs, per-run failure isolation, estimated
cost, synthesis, owner isolation, validation-before-stream and SSE event shape.
"""

import json
from uuid import UUID, uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from app.api.v1.compare import compare_http
from app.core.credential_vault import CredentialVault
from app.models.base import utcnow
from app.services.ai.chat import ChatHTTP

BASE = "/api/v1/ai/compare"
KEY = "contract-only-compare-key"
MODEL_A = "model-a"
MODEL_B = "model-b"


def chunk(text):
    return {"choices": [{"delta": {"content": text}}]}


def sse(*events):
    parts = []
    for event in events:
        data = "[DONE]" if event == "[DONE]" else json.dumps(event)
        parts.append(f"data: {data}\n\n")
    return "".join(parts)


STREAM_A = sse(
    chunk("Answer"),
    chunk(" A"),
    {"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 3}},
    "[DONE]",
)
STREAM_B = sse(
    chunk("Answer B"),
    {"choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 2}},
    "[DONE]",
)


def parse_sse(text):
    events = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        name = data = None
        for line in block.split("\n"):
            if line.startswith("event: "):
                name = line[len("event: ") :]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: ") :])
        events.append((name, data))
    return events


@pytest.fixture(autouse=True)
def compare_settings(settings):
    settings.credential_encryption_key = SecretStr(Fernet.generate_key().decode())
    return settings


@pytest.fixture
def owner(client, register):
    assert register(client).status_code == 201
    return client


@pytest.fixture
def owner_id(owner):
    return UUID(owner.get("/api/v1/auth/me").json()["id"])


@pytest.fixture
def mock_compare(app):
    def configure(handler=None):
        def default(request):
            payload = json.loads(request.content)
            if payload.get("model") == MODEL_B:
                return httpx.Response(200, text=STREAM_B)
            return httpx.Response(200, text=STREAM_A)

        handler = handler or default
        app.dependency_overrides[compare_http] = lambda: ChatHTTP(
            transport=httpx.MockTransport(handler)
        )

    configure()
    return configure


async def seed(
    db, settings, user_id, *, provider="openai", model_id=MODEL_A, enabled=True,
    chat=None, price_in=None, price_out=None,
):
    vault = CredentialVault(settings.credential_encryption_key)
    now = utcnow()
    credential = await db.user_provider_credentials.find_one(
        {"user_id": user_id, "provider": provider}
    )
    if credential is None:
        credential_id = uuid4()
        await db.user_provider_credentials.insert_one(
            {
                "_id": credential_id, "user_id": user_id, "provider": provider,
                "encrypted_api_key": vault.encrypt(SecretStr(KEY), user_id, provider),
                "enabled": enabled, "default_model": None, "connection_status": "connected",
                "last_checked_at": now, "models_synced_at": now, "last_error_code": None,
                "revision": 1, "created_at": now, "updated_at": now,
            }
        )
    else:
        credential_id = credential["_id"]
    await db.ai_models.insert_one(
        {
            "_id": uuid4(), "credential_id": credential_id, "model_id": model_id,
            "display_name": model_id, "description": None,
            "capabilities": {"chat": chat, "streaming": None, "tools": None, "embeddings": None},
            "input_token_limit": None, "output_token_limit": None,
            "capability_source": "unknown",
            "input_price_per_token": price_in, "output_price_per_token": price_out,
            "created_at": now,
        }
    )
    return model_id


def create(client, targets=None, **fields):
    targets = targets or [
        {"provider": "openai", "model": MODEL_A},
        {"provider": "openai", "model": MODEL_B},
    ]
    response = client.post(
        f"{BASE}/comparisons",
        json={"prompt": "So sánh A và B", "targets": targets, **fields},
    )
    assert response.status_code == 201, response.text
    return response.json()


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    assert response.json()["detail"]["code"] == code
    assert KEY not in response.text


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/comparisons", None),
        (
            "POST",
            "/comparisons",
            {"prompt": "x", "targets": [{"provider": "openai", "model": MODEL_A}] * 2},
        ),
        ("GET", f"/comparisons/{uuid4()}", None),
        ("DELETE", f"/comparisons/{uuid4()}", None),
        ("POST", f"/comparisons/{uuid4()}/execute", None),
        ("POST", f"/comparisons/{uuid4()}/synthesize", {"provider": "openai", "model": MODEL_A}),
    ],
)
def test_all_compare_routes_require_auth(client, method, path, body):
    response = client.request(method, BASE + path, json=body)
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


def test_create_rejects_invalid_target_counts_and_duplicates(owner):
    def post(targets, prompt="x"):
        return owner.post(f"{BASE}/comparisons", json={"prompt": prompt, "targets": targets})

    one = [{"provider": "openai", "model": MODEL_A}]
    assert post(one).status_code == 422
    dup = [{"provider": "openai", "model": MODEL_A}] * 2
    assert post(dup).status_code == 422
    five = [{"provider": "openai", "model": f"m{i}"} for i in range(5)]
    assert post(five).status_code == 422
    assert post(one * 2, prompt="   ").status_code == 422


async def test_create_validates_sync_capability_and_ownership(owner, owner_id, db, settings):
    await seed(db, settings, owner_id, model_id=MODEL_A)
    # model-b not synced yet
    resp = owner.post(f"{BASE}/comparisons", json={"prompt": "x", "targets": [
        {"provider": "openai", "model": MODEL_A}, {"provider": "openai", "model": MODEL_B}]})
    assert_error(resp, 409, "model_not_synced")
    # non-chat model
    await seed(db, settings, owner_id, model_id=MODEL_B, chat=False)
    resp = owner.post(f"{BASE}/comparisons", json={"prompt": "x", "targets": [
        {"provider": "openai", "model": MODEL_A}, {"provider": "openai", "model": MODEL_B}]})
    assert_error(resp, 409, "model_not_chat_capable")


async def test_execute_streams_parallel_runs_and_isolates_failure(
    owner, owner_id, db, settings, mock_compare
):
    await seed(db, settings, owner_id, model_id=MODEL_A)
    await seed(db, settings, owner_id, model_id=MODEL_B)

    def handler(request):
        payload = json.loads(request.content)
        if payload.get("model") == MODEL_B:
            return httpx.Response(400, json={"error": {"message": "boom"}})
        return httpx.Response(200, text=STREAM_A)

    mock_compare(handler)
    comp = create(owner)
    response = owner.post(f"{BASE}/comparisons/{comp['id']}/execute")
    assert response.status_code == 200
    events = parse_sse(response.text)
    names = [name for name, _ in events]
    assert names[0] == "comparison"
    assert names[-1] == "done"
    assert "run_delta" in names
    done_runs = [data["run"] for name, data in events if name == "run_done"]
    error_runs = [data["run"] for name, data in events if name == "run_error"]
    assert len(done_runs) == 1 and done_runs[0]["model"] == MODEL_A
    assert done_runs[0]["content"] == "Answer A"
    assert len(error_runs) == 1 and error_runs[0]["model"] == MODEL_B
    # A structured HTTP 400 rejection now surfaces its real classified code
    # (provider_request_rejected) instead of the old generic generation_failed.
    assert error_runs[0]["error_code"] == "provider_request_rejected"
    final = events[-1][1]["comparison"]
    statuses = {r["model"]: r["status"] for r in final["runs"]}
    assert statuses == {MODEL_A: "success", MODEL_B: "error"}
    assert KEY not in response.text


async def test_execute_estimated_cost_from_pricing(owner, owner_id, db, settings, mock_compare):
    await seed(db, settings, owner_id, model_id=MODEL_A, price_in=1e-6, price_out=2e-6)
    await seed(db, settings, owner_id, model_id=MODEL_B)
    comp = create(owner)
    response = owner.post(f"{BASE}/comparisons/{comp['id']}/execute")
    events = parse_sse(response.text)
    runs = {r["model"]: r for r in events[-1][1]["comparison"]["runs"]}
    # 7 input * 1e-6 + 3 output * 2e-6 = 1.3e-5
    assert runs[MODEL_A]["estimated_cost"] == pytest.approx(1.3e-5)
    # model-b has no pricing -> no estimate
    assert runs[MODEL_B]["estimated_cost"] is None


async def test_synthesis_requires_success_and_streams(owner, owner_id, db, settings, mock_compare):
    await seed(db, settings, owner_id, model_id=MODEL_A)
    await seed(db, settings, owner_id, model_id=MODEL_B)
    comp = create(owner)
    synth_url = f"{BASE}/comparisons/{comp['id']}/synthesize"
    synth_body = {"provider": "openai", "model": MODEL_A}
    # No successful runs yet -> 409
    resp = owner.post(synth_url, json=synth_body)
    assert_error(resp, 409, "no_successful_runs")
    owner.post(f"{BASE}/comparisons/{comp['id']}/execute")
    resp = owner.post(synth_url, json=synth_body)
    assert resp.status_code == 200
    events = parse_sse(resp.text)
    names = [name for name, _ in events]
    assert "synthesis_delta" in names and "synthesis_done" in names and names[-1] == "done"
    synthesis = events[-1][1]["comparison"]["synthesis"]
    assert synthesis["status"] == "success" and synthesis["content"] == "Answer A"


async def test_owner_isolation_and_delete(
    owner, owner_id, db, settings, mock_compare, client_factory, register
):
    await seed(db, settings, owner_id, model_id=MODEL_A)
    await seed(db, settings, owner_id, model_id=MODEL_B)
    comp = create(owner)
    other = client_factory()
    assert register(other, email="other@example.com").status_code == 201
    assert other.get(f"{BASE}/comparisons/{comp['id']}").status_code == 404
    assert other.post(f"{BASE}/comparisons/{comp['id']}/execute").status_code == 404
    assert other.delete(f"{BASE}/comparisons/{comp['id']}").status_code == 404
    assert owner.delete(f"{BASE}/comparisons/{comp['id']}").status_code == 204
    assert owner.get(f"{BASE}/comparisons/{comp['id']}").status_code == 404


async def test_list_and_get_shape(owner, owner_id, db, settings, mock_compare):
    await seed(db, settings, owner_id, model_id=MODEL_A)
    await seed(db, settings, owner_id, model_id=MODEL_B)
    comp = create(owner, title="Tiêu đề")
    listing = owner.get(f"{BASE}/comparisons").json()["comparisons"]
    assert len(listing) == 1
    assert listing[0]["title"] == "Tiêu đề"
    assert {t["model"] for t in listing[0]["targets"]} == {MODEL_A, MODEL_B}
    detail = owner.get(f"{BASE}/comparisons/{comp['id']}").json()
    assert detail["prompt"] == "So sánh A và B"
    assert len(detail["runs"]) == 2
    assert all(r["status"] == "pending" for r in detail["runs"])