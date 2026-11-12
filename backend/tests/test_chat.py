"""Authenticated chat API contract tests over the offline MongoDB mock.

Generation is intercepted by httpx.MockTransport, so nothing here proves a live
provider call. Fixture text is contract-only. These verify routing, owner
isolation, validation-before-stream, SSE event shape, persistence and redaction.
"""

import json
from uuid import UUID, uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from app.api.v1.chat import chat_http
from app.core.credential_vault import CredentialVault
from app.models.base import utcnow
from app.schemas.chat import DEFAULT_TITLE
from app.services.ai.chat import ChatHTTP

BASE = "/api/v1/ai/chat"
KEY = "contract-only-chat-key"
MODEL = "chat-model"


def chunk(text):
    return {"choices": [{"delta": {"content": text}}]}


def sse(*events):
    parts = []
    for event in events:
        data = "[DONE]" if event == "[DONE]" else json.dumps(event)
        parts.append(f"data: {data}\n\n")
    return "".join(parts)


DEFAULT_STREAM = sse(
    chunk("Hello"),
    chunk(" world"),
    {"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 3}},
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
def chat_settings(settings):
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
def mock_chat(app):
    def configure(handler=None):
        handler = handler or (lambda _: httpx.Response(200, text=DEFAULT_STREAM))
        app.dependency_overrides[chat_http] = lambda: ChatHTTP(
            transport=httpx.MockTransport(handler)
        )

    configure()
    return configure


async def seed(
    db,
    settings,
    user_id,
    *,
    provider="openai",
    model_id=MODEL,
    enabled=True,
    chat=None,
    key=KEY,
):
    """Insert an encrypted credential plus one synced model directly (owner-bound)."""
    vault = CredentialVault(settings.credential_encryption_key)
    now = utcnow()
    credential_id = uuid4()
    await db.user_provider_credentials.insert_one(
        {
            "_id": credential_id,
            "user_id": user_id,
            "provider": provider,
            "encrypted_api_key": vault.encrypt(SecretStr(key), user_id, provider),
            "enabled": enabled,
            "default_model": None,
            "connection_status": "connected",
            "last_checked_at": now,
            "models_synced_at": now,
            "last_error_code": None,
            "revision": 1,
            "created_at": now,
            "updated_at": now,
        }
    )
    await db.ai_models.insert_one(
        {
            "_id": uuid4(),
            "credential_id": credential_id,
            "model_id": model_id,
            "display_name": model_id,
            "description": None,
            "capabilities": {"chat": chat, "streaming": None, "tools": None, "embeddings": None},
            "input_token_limit": None,
            "output_token_limit": None,
            "capability_source": "unknown",
            "created_at": now,
        }
    )
    return model_id


def create(client, provider="openai", model=MODEL, **fields):
    response = client.post(
        f"{BASE}/conversations", json={"provider": provider, "model": model, **fields}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def send(client, conversation_id, content="hi"):
    return client.post(
        f"{BASE}/conversations/{conversation_id}/messages", json={"content": content}
    )


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    assert response.json()["detail"]["code"] == code
    assert response.headers["cache-control"] == "no-store"
    assert KEY not in response.text


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/conversations", None),
        ("POST", "/conversations", {"provider": "openai", "model": MODEL}),
        ("GET", f"/conversations/{uuid4()}", None),
        ("PATCH", f"/conversations/{uuid4()}", {"title": "x"}),
        ("DELETE", f"/conversations/{uuid4()}", None),
        ("POST", f"/conversations/{uuid4()}/messages", {"content": "hi"}),
        ("POST", f"/conversations/{uuid4()}/regenerate", None),
    ],
)
def test_all_chat_routes_require_auth(client, method, path, body):
    response = client.request(method, BASE + path, json=body)
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"provider": "openai"},
        {"provider": "openai", "model": MODEL, "temperature": 3},
        {"provider": "openai", "model": MODEL, "temperature": -1},
        {"provider": "openai", "model": MODEL, "max_output_tokens": 0},
        {"provider": "openai", "model": MODEL, "max_output_tokens": 99999},
        {"provider": "openai", "model": MODEL, "title": ""},
        {"provider": "openai", "model": MODEL, "system_prompt": "x" * 8001},
        {"provider": "openai", "model": MODEL, "extra": "field"},
        {"provider": "openai", "model": MODEL, "api_key": KEY},
    ],
)
def test_create_validation_rejects_and_redacts(owner, body):
    assert_error(
        owner.post(f"{BASE}/conversations", json=body), 422, "invalid_provider_configuration"
    )


@pytest.mark.parametrize(
    "provider,code,status",
    [
        ("unknown", "provider_not_found", 404),
        ("anthropic", "provider_not_implemented", 409),
        ("openai", "credentials_missing", 409),
    ],
)
def test_create_requires_implemented_configured_provider(owner, provider, code, status):
    assert_error(
        owner.post(f"{BASE}/conversations", json={"provider": provider, "model": MODEL}),
        status,
        code,
    )


async def test_create_requires_synced_model(owner, owner_id, db, settings):
    await seed(db, settings, owner_id)
    assert_error(
        owner.post(f"{BASE}/conversations", json={"provider": "openai", "model": "unsynced"}),
        409,
        "model_not_synced",
    )


async def test_conversation_lifecycle(owner, owner_id, db, settings):
    await seed(db, settings, owner_id)
    conversation_id = create(owner, title="Ban đầu", system_prompt="Be brief.", temperature=0.4)
    listing = owner.get(f"{BASE}/conversations").json()["conversations"]
    assert [c["id"] for c in listing] == [conversation_id]
    detail = owner.get(f"{BASE}/conversations/{conversation_id}").json()
    assert detail["title"] == "Ban đầu"
    assert detail["system_prompt"] == "Be brief."
    assert detail["messages"] == []

    patched = owner.patch(
        f"{BASE}/conversations/{conversation_id}", json={"title": "Đã đổi"}
    ).json()
    assert patched["title"] == "Đã đổi"
    assert patched["system_prompt"] == "Be brief."  # untouched fields preserved

    assert owner.delete(f"{BASE}/conversations/{conversation_id}").status_code == 204
    assert_error(
        owner.get(f"{BASE}/conversations/{conversation_id}"), 404, "conversation_not_found"
    )
    assert owner.get(f"{BASE}/conversations").json()["conversations"] == []


async def test_default_title_and_patch_validation(owner, owner_id, db, settings):
    await seed(db, settings, owner_id)
    conversation_id = create(owner)
    assert owner.get(f"{BASE}/conversations/{conversation_id}").json()["title"] == DEFAULT_TITLE
    for body in [{}, {"title": None}, {"title": ""}, {"temperature": 5}, {"unknown": 1}]:
        assert_error(
            owner.patch(f"{BASE}/conversations/{conversation_id}", json=body),
            422,
            "invalid_provider_configuration",
        )


async def test_owner_isolation(owner, owner_id, db, settings, client_factory, register):
    await seed(db, settings, owner_id)
    conversation_id = create(owner)
    other = client_factory()
    assert register(other, email="other@example.com").status_code == 201
    assert other.get(f"{BASE}/conversations").json()["conversations"] == []
    assert_error(
        other.get(f"{BASE}/conversations/{conversation_id}"), 404, "conversation_not_found"
    )
    assert_error(
        other.patch(f"{BASE}/conversations/{conversation_id}", json={"title": "x"}),
        404,
        "conversation_not_found",
    )
    assert_error(
        other.delete(f"{BASE}/conversations/{conversation_id}"), 404, "conversation_not_found"
    )
    assert_error(send(other, conversation_id), 404, "conversation_not_found")


async def test_send_streams_persists_and_records_usage(owner, owner_id, db, settings, mock_chat):
    await seed(db, settings, owner_id)
    conversation_id = create(owner)
    response = send(owner, conversation_id, "Xin chào")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-store"
    assert KEY not in response.text

    events = parse_sse(response.text)
    assert events[0][0] == "user_message"
    assert events[0][1]["message"]["role"] == "user"
    assert events[0][1]["message"]["content"] == "Xin chào"
    assert [data["text"] for name, data in events if name == "delta"] == ["Hello", " world"]
    assert events[-1][0] == "done"
    assistant = events[-1][1]["message"]
    assert assistant["role"] == "assistant"
    assert assistant["content"] == "Hello world"
    assert assistant["status"] == "success"
    assert assistant["model"] == MODEL
    assert (assistant["input_tokens"], assistant["output_tokens"]) == (7, 3)
    assert isinstance(assistant["latency_ms"], int) and assistant["latency_ms"] >= 0

    messages = [doc async for doc in db.messages.find({"conversation_id": UUID(conversation_id)})]
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "Xin chào"),
        ("assistant", "Hello world"),
    ]
    requests = [doc async for doc in db.ai_requests.find({})]
    assert len(requests) == 1
    assert requests[0]["status"] == "success"
    assert (requests[0]["input_tokens"], requests[0]["output_tokens"]) == (7, 3)
    assert requests[0]["message_id"] == UUID(assistant["id"])
    # First user message auto-titles the conversation.
    assert owner.get(f"{BASE}/conversations/{conversation_id}").json()["title"] == "Xin chào"


@pytest.mark.parametrize("content", ["", "   ", "\n\t "])
async def test_send_rejects_empty_before_stream(owner, owner_id, db, settings, mock_chat, content):
    await seed(db, settings, owner_id)
    conversation_id = create(owner)
    assert_error(send(owner, conversation_id, content), 422, "invalid_provider_configuration")
    assert [doc async for doc in db.messages.find({})] == []


async def test_send_unknown_conversation_is_http_error(owner, mock_chat):
    response = owner.post(f"{BASE}/conversations/{uuid4()}/messages", json={"content": "hi"})
    assert_error(response, 404, "conversation_not_found")
    assert response.headers["content-type"].startswith("application/json")


async def test_send_blocks_non_chat_model_before_stream(owner, owner_id, db, settings, mock_chat):
    await seed(db, settings, owner_id, provider="gemini", chat=False)
    conversation_id = create(owner, provider="gemini")
    response = send(owner, conversation_id)
    assert_error(response, 409, "model_not_chat_capable")
    assert response.headers["content-type"].startswith("application/json")
    assert [doc async for doc in db.messages.find({})] == []


async def test_send_requires_enabled_credential_and_synced_model(
    owner, owner_id, db, settings, mock_chat
):
    await seed(db, settings, owner_id)
    conversation_id = create(owner)
    await db.user_provider_credentials.update_one({}, {"$set": {"enabled": False}})
    assert_error(send(owner, conversation_id), 409, "provider_disabled")
    await db.user_provider_credentials.update_one({}, {"$set": {"enabled": True}})
    await db.ai_models.delete_many({})
    assert_error(send(owner, conversation_id), 409, "model_not_synced")
    await db.user_provider_credentials.delete_many({})
    assert_error(send(owner, conversation_id), 409, "credentials_missing")


async def test_provider_runtime_error_becomes_sse_error_event(
    owner, owner_id, db, settings, mock_chat
):
    await seed(db, settings, owner_id)
    conversation_id = create(owner)
    mock_chat(lambda _: httpx.Response(401, text=KEY))
    response = send(owner, conversation_id)
    assert response.status_code == 200
    assert KEY not in response.text
    events = parse_sse(response.text)
    assert events[0][0] == "user_message"
    assert events[-1] == (
        "error",
        {
            "code": "provider_authentication_failed",
            "message": "The provider rejected the saved API key.",
        },
    )
    assistant = [doc async for doc in db.messages.find({"role": "assistant"})][0]
    assert assistant["status"] == "error"
    assert assistant["error_code"] == "provider_authentication_failed"
    assert assistant["content"] == ""


async def test_echoed_credential_in_stream_is_redacted(owner, owner_id, db, settings, mock_chat):
    await seed(db, settings, owner_id)
    conversation_id = create(owner)
    mock_chat(lambda _: httpx.Response(200, text=sse(chunk(KEY), "[DONE]")))
    response = send(owner, conversation_id)
    assert response.status_code == 200
    assert KEY not in response.text
    events = parse_sse(response.text)
    assert not any(name == "delta" for name, _ in events)
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "generation_failed"


async def test_regenerate_replaces_last_assistant(owner, owner_id, db, settings, mock_chat):
    await seed(db, settings, owner_id)
    conversation_id = create(owner)
    send(owner, conversation_id, "Câu hỏi")
    mock_chat(lambda _: httpx.Response(200, text=sse(chunk("Regenerated"), "[DONE]")))
    response = owner.post(f"{BASE}/conversations/{conversation_id}/regenerate")
    assert response.status_code == 200
    events = parse_sse(response.text)
    assert not any(name == "user_message" for name, _ in events)
    assert [data["text"] for name, data in events if name == "delta"] == ["Regenerated"]
    assert events[-1][0] == "done"
    cursor = db.messages.find({"conversation_id": UUID(conversation_id)}).sort("created_at", 1)
    messages = [doc async for doc in cursor]
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "Câu hỏi"),
        ("assistant", "Regenerated"),
    ]
    assert len([doc async for doc in db.ai_requests.find({})]) == 2


async def test_regenerate_without_user_message_is_http_error(
    owner, owner_id, db, settings, mock_chat
):
    await seed(db, settings, owner_id)
    conversation_id = create(owner)
    assert_error(
        owner.post(f"{BASE}/conversations/{conversation_id}/regenerate"), 422, "empty_message"
    )


async def test_delete_conversation_removes_messages(owner, owner_id, db, settings, mock_chat):
    await seed(db, settings, owner_id)
    conversation_id = create(owner)
    send(owner, conversation_id)
    assert len([doc async for doc in db.messages.find({})]) == 2
    assert owner.delete(f"{BASE}/conversations/{conversation_id}").status_code == 204
    assert [doc async for doc in db.messages.find({})] == []


def test_chat_mutation_rejects_untrusted_origin(owner):
    response = owner.post(
        f"{BASE}/conversations",
        json={"provider": "openai", "model": MODEL},
        headers={"Origin": "https://attacker.invalid"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "invalid_origin"
    assert response.headers["cache-control"] == "no-store"


def test_chat_application_rate_limit_has_safe_detail(owner, app):
    app.state.rate_limiter.settings.api_rate_limit = 1
    assert_error(owner.get(f"{BASE}/conversations"), 429, "request_rate_limited")