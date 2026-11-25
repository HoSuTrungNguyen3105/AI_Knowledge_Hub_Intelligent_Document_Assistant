"""Project Discussion contract tests (offline, mock provider).

Mirrors the collab/workflow harness: the provider is mocked at the
HTTP transport, agents run through the real Phase 5 AgentService, and
discussion state lives in mongomock collections. Covers the spec's
core cases: mention routing by real Agent ID, project context in the
prompt, no-mention auto-routing, failed reply + retry without
duplicates, the decision lifecycle with supersede, convert-to-task,
and owner scoping.
"""

from uuid import UUID, uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from test_compare import MODEL_A, chunk, seed, sse

from app.api.v1.agents import agent_http
from app.services.ai.chat import ChatHTTP

PROJECTS = "/api/v1/ai/projects"


@pytest.fixture(autouse=True)
def encryption(settings):
    settings.credential_encryption_key = SecretStr(Fernet.generate_key().decode())


@pytest.fixture
def mock_http(app):
    state = {"handler": None, "calls": []}

    def configure(handler=None):
        state["handler"] = handler

    def make():
        def handler(request):
            state["calls"].append(request)
            if state["handler"]:
                return state["handler"](request, len(state["calls"]))
            return httpx.Response(200, text=sse(chunk("Done."), "[DONE]"))

        return ChatHTTP(transport=httpx.MockTransport(handler))

    app.dependency_overrides[agent_http] = make
    state["configure"] = configure
    return state


@pytest.fixture
async def owner(client, register, db, settings):
    assert register(client).status_code == 201
    owner_id = UUID(client.get("/api/v1/auth/me").json()["id"])
    await seed(db, settings, owner_id)
    return client, owner_id


def make_agent(client, name):
    r = client.post(
        "/api/v1/ai/agents",
        json={"name": name, "provider": "openai", "model": MODEL_A, "tools": []},
    )
    assert r.status_code == 201, r.text
    return r.json()


def make_project(client, name="SmartBiz AI"):
    r = client.post(
        PROJECTS,
        json={"name": name, "description": "Nền tảng quản trị doanh nghiệp."},
    )
    assert r.status_code == 201, r.text
    return r.json()


def reply_handler(text):
    def handler(request, n):
        return httpx.Response(200, text=sse(chunk(text), "[DONE]"))

    return handler


async def test_mention_one_agent_replies_with_project_context(owner, mock_http):
    client, _ = owner
    architect = make_agent(client, "Architect")
    make_agent(client, "Developer")
    project = make_project(client)
    mock_http["configure"](reply_handler("Nên dùng Modular Monolith cho MVP."))

    r = client.post(
        f"{PROJECTS}/{project['id']}/discussion",
        json={
            "content": "Monolith hay microservices cho MVP?",
            "mention_agent_ids": [architect["id"]],
        },
    )
    assert r.status_code == 201, r.text
    messages = r.json()["messages"]
    assert [m["sender_type"] for m in messages] == ["user", "agent"]
    reply = messages[1]
    assert reply["agent_name"] == "Architect"
    assert "Modular Monolith" in reply["content"]
    assert reply["status"] == "done"
    # Only the mentioned agent was called, with the project in context.
    assert mock_http["calls"]
    bodies = "".join(
        call.content.decode("utf-8", "ignore") for call in mock_http["calls"]
    )
    assert "SmartBiz AI" in bodies

    listed = client.get(f"{PROJECTS}/{project['id']}/discussion")
    assert listed.status_code == 200
    assert len(listed.json()["messages"]) == 2  # history survives reload


async def test_mention_unknown_agent_is_404(owner, mock_http):
    client, _ = owner
    project = make_project(client)
    r = client.post(
        f"{PROJECTS}/{project['id']}/discussion",
        json={"content": "Hi", "mention_agent_ids": [str(uuid4())]},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "agent_not_found"


async def test_no_mention_auto_routes_to_architect(owner, mock_http):
    client, _ = owner
    make_agent(client, "Architect")
    make_agent(client, "Developer")
    project = make_project(client)
    mock_http["configure"](reply_handler("Ý kiến của tôi về kiến trúc."))
    r = client.post(
        f"{PROJECTS}/{project['id']}/discussion",
        json={"content": "Kiến trúc hệ thống nên là monolith hay microservices?"},
    )
    assert r.status_code == 201, r.text
    agent_names = [
        m["agent_name"] for m in r.json()["messages"] if m["sender_type"] == "agent"
    ]
    assert agent_names and agent_names[0] == "Architect"


async def test_failed_reply_then_retry_without_duplicates(owner, mock_http):
    client, _ = owner
    tester = make_agent(client, "QA Tester")
    project = make_project(client)

    def failing(request, n):
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    mock_http["configure"](failing)
    r = client.post(
        f"{PROJECTS}/{project['id']}/discussion",
        json={"content": "Kiểm thử giúp tôi.", "mention_agent_ids": [tester["id"]]},
    )
    assert r.status_code == 201, r.text
    messages = r.json()["messages"]
    assert messages[1]["status"] == "error" and messages[1]["error_code"]
    user_message_id = messages[0]["id"]

    mock_http["configure"](reply_handler("Đã rõ, tôi sẽ kiểm thử theo checklist."))
    retried = client.post(
        f"{PROJECTS}/{project['id']}/discussion/{user_message_id}/retry"
    )
    assert retried.status_code == 200, retried.text
    replies = retried.json()["messages"]
    assert len(replies) == 1 and replies[0]["status"] == "done"

    listed = client.get(f"{PROJECTS}/{project['id']}/discussion").json()["messages"]
    assert [m["status"] for m in listed] == ["done", "done"]  # error copy is gone
    again = client.post(
        f"{PROJECTS}/{project['id']}/discussion/{user_message_id}/retry"
    )
    assert again.status_code == 422
    assert again.json()["detail"]["code"] == "discussion_nothing_to_retry"


async def test_decision_lifecycle_with_supersede(owner):
    client, _ = owner
    project = make_project(client)
    base = f"{PROJECTS}/{project['id']}/decisions"

    first = client.post(base, json={"title": "Dùng Microservices", "reason": "Mở rộng tốt"})
    assert first.status_code == 201, first.text
    first = first.json()
    assert first["status"] == "proposed" and len(first["status_history"]) == 1

    approved = client.patch(f"{base}/{first['id']}", json={"status": "approved"})
    assert approved.status_code == 200 and approved.json()["status"] == "approved"

    second = client.post(
        base, json={"title": "Dùng Modular Monolith", "reason": "Đơn giản cho MVP"}
    ).json()
    replaced = client.patch(
        f"{base}/{second['id']}",
        json={"status": "approved", "supersedes_id": first["id"]},
    )
    assert replaced.status_code == 200, replaced.text

    decisions = client.get(base).json()["decisions"]
    by_title = {d["title"]: d for d in decisions}
    assert by_title["Dùng Microservices"]["status"] == "superseded"
    assert by_title["Dùng Microservices"]["status_history"][-1]["status"] == "superseded"
    assert by_title["Dùng Modular Monolith"]["status"] == "approved"


async def test_convert_message_to_task(owner):
    client, _ = owner
    project = make_project(client)
    posted = client.post(
        f"{PROJECTS}/{project['id']}/discussion",
        json={"content": "Cần thiết kế lại database cho ERP."},
    )
    assert posted.status_code == 201, posted.text
    message_id = posted.json()["messages"][0]["id"]

    converted = client.post(
        f"{PROJECTS}/{project['id']}/discussion/{message_id}/convert-task",
        json={
            "title": "Design ERP Database Schema",
            "acceptance_criteria": "Schema qua review của Architect",
            "suggested_type": "ai",
        },
    )
    assert converted.status_code == 201, converted.text
    assert converted.json()["task_title"] == "Design ERP Database Schema"

    analyses = client.get(f"{PROJECTS}/{project['id']}/analyses").json()["analyses"]
    assert len(analyses) == 1 and analyses[0]["provider"] == "discussion"
    task = analyses[0]["tasks"][0]
    assert task["title"] == "Design ERP Database Schema"
    assert task["acceptance_criteria"] == "Schema qua review của Architect"

    missing = client.post(
        f"{PROJECTS}/{project['id']}/discussion/{uuid4()}/convert-task", json={}
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "discussion_message_not_found"


async def test_discussion_is_owner_scoped(owner, client_factory, register, db, settings):
    client, _ = owner
    project = make_project(client)
    other = client_factory()
    assert register(other).status_code == 201
    other_id = UUID(other.get("/api/v1/auth/me").json()["id"])
    await seed(db, settings, other_id)

    r = other.get(f"{PROJECTS}/{project['id']}/discussion")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "project_not_found"
