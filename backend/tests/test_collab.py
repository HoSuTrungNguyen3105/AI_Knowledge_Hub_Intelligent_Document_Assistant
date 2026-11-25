"""Offline contracts for collaboration rooms (NEXORA Module 03, v1).

Rooms live on the multi_chats collection with member Agents; messages
live in collab_messages. Covers room CRUD + member validation, plain
messages, @mention validation, a full mention round-trip against a
mocked provider (the reply is stored in the room with token usage and
the room transcript reaches the Agent), and owner isolation.
"""

from uuid import UUID

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from test_compare import MODEL_A, MODEL_B, chunk, seed, sse

from app.api.v1.agents import agent_http
from app.services.ai.chat import ChatHTTP

BASE = "/api/v1/ai/collab/rooms"
AGENTS = "/api/v1/ai/agents"


@pytest.fixture(autouse=True)
def encryption(settings):
    settings.credential_encryption_key = SecretStr(Fernet.generate_key().decode())


@pytest.fixture
async def owner(client, register, db, settings):
    assert register(client).status_code == 201
    owner_id = UUID(client.get("/api/v1/auth/me").json()["id"])
    await seed(db, settings, owner_id, price_in=0.000001, price_out=0.000002)
    return client, owner_id


@pytest.fixture
def mock_agent(app):
    def configure(handler=None):
        default = httpx.Response(200, text=sse(chunk("Xin chào từ Agent"), "[DONE]"))
        handler = handler or (lambda _: default)
        app.dependency_overrides[agent_http] = lambda: ChatHTTP(
            transport=httpx.MockTransport(handler)
        )
    configure()
    return configure


def create_agent(client, name="Agent A", model=MODEL_A):
    response = client.post(
        AGENTS,
        json={
            "name": name,
            "provider": "openai",
            "model": model,
            "system_prompt": "Help.",
            "tools": [],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_room(client, agent_ids=(), title="Phòng dự án"):
    response = client.post(BASE, json={"title": title, "agent_ids": list(agent_ids)})
    assert response.status_code == 201, response.text
    return response.json()


def test_collab_requires_auth(client):
    assert client.get(BASE).status_code == 401


async def test_room_crud_and_members(owner):
    client, _ = owner
    agent = create_agent(client)
    room = create_room(client, [agent["id"]])
    assert room["title"] == "Phòng dự án"
    assert room["agents"][0]["name"] == "Agent A"
    assert room["message_count"] == 0

    renamed = client.patch(f"{BASE}/{room['id']}", json={"title": "Phòng mới", "agent_ids": []})
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Phòng mới"
    assert renamed.json()["agents"] == []

    assert client.delete(f"{BASE}/{room['id']}").status_code == 204
    assert client.get(f"{BASE}/{room['id']}").status_code == 404


async def test_room_rejects_unknown_agent(owner):
    client, _ = owner
    from uuid import uuid4

    response = client.post(BASE, json={"title": "X", "agent_ids": [str(uuid4())]})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "agent_not_found"


async def test_plain_message_and_mention_validation(owner):
    client, _ = owner
    member = create_agent(client, "Trong phòng")
    outsider = create_agent(client, "Ngoài phòng")
    room = create_room(client, [member["id"]])

    posted = client.post(
        f"{BASE}/{room['id']}/messages",
        json={"content": "Ghi chú chung", "mention_agent_ids": []},
    )
    assert posted.status_code == 201, posted.text
    assert len(posted.json()["messages"]) == 1
    assert posted.json()["messages"][0]["sender_type"] == "user"

    bad = client.post(
        f"{BASE}/{room['id']}/messages",
        json={"content": "Ê bạn ngoài", "mention_agent_ids": [outsider["id"]]},
    )
    assert bad.status_code == 422
    assert bad.json()["detail"]["code"] == "collab_agent_not_member"

    messages = client.get(f"{BASE}/{room['id']}/messages").json()["messages"]
    assert len(messages) == 1  # the rejected post stored nothing


async def test_mention_runs_agent_and_stores_reply(owner, mock_agent, db):
    client, owner_id = owner
    seen_prompts = []

    def handler(request):
        import json

        body = json.loads(request.content)
        seen_prompts.append(body["messages"][-1]["content"])
        return httpx.Response(200, text=sse(chunk("Tôi đã rõ nhiệm vụ"), "[DONE]"))

    mock_agent(handler)
    agent = create_agent(client)
    room = create_room(client, [agent["id"]])

    client.post(
        f"{BASE}/{room['id']}/messages",
        json={"content": "Bối cảnh ban đầu", "mention_agent_ids": []},
    )
    posted = client.post(
        f"{BASE}/{room['id']}/messages",
        json={"content": "Hãy bắt đầu việc A", "mention_agent_ids": [agent["id"]]},
    )
    assert posted.status_code == 201, posted.text
    messages = posted.json()["messages"]
    assert len(messages) == 2
    reply = messages[1]
    assert reply["sender_type"] == "agent"
    assert reply["agent_name"] == "Agent A"
    assert reply["content"] == "Tôi đã rõ nhiệm vụ"
    assert reply["status"] == "done"
    assert "Bối cảnh ban đầu" in seen_prompts[0]  # transcript reached the agent
    assert "Hãy bắt đầu việc A" in seen_prompts[0]

    detail = client.get(f"{BASE}/{room['id']}").json()
    assert detail["message_count"] == 3
    stored = await db.collab_messages.count_documents({"room_id": UUID(room["id"])})
    assert stored == 3
    assert owner_id  # owner fixture sanity


async def test_rooms_are_owner_scoped(owner, client_factory, register):
    client, _ = owner
    room = create_room(client)
    stranger = client_factory()
    assert register(stranger, email="stranger3@example.com").status_code == 201
    assert stranger.get(BASE).json()["rooms"] == []
    assert stranger.get(f"{BASE}/{room['id']}").status_code == 404
    response = stranger.post(
        f"{BASE}/{room['id']}/messages", json={"content": "alo"}
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "collab_room_not_found"


async def test_second_mentioned_agent_sees_first_reply(owner, mock_agent, db, settings):
    """ARCH-RESULT-739 — the core Agent-to-Agent proof: in ONE post
    mentioning A then B, B's prompt must contain A's stored reply, and
    B's message records A's message in its context ids."""
    client, owner_id = owner
    await seed(db, settings, owner_id, model_id=MODEL_B)
    prompts = {}

    def handler(request):
        import json

        body = json.loads(request.content)
        prompt = body["messages"][-1]["content"]
        if body["model"] == MODEL_A:
            return httpx.Response(
                200, text=sse(chunk("Kiến trúc đề xuất: ARCH-RESULT-739"), "[DONE]")
            )
        prompts["b"] = prompt
        text = (
            "Tôi thấy ARCH-RESULT-739 và phản biện như sau"
            if "ARCH-RESULT-739" in prompt
            else "Tôi không thấy kết quả nào của Agent khác"
        )
        return httpx.Response(200, text=sse(chunk(text), "[DONE]"))

    mock_agent(handler)
    agent_a = create_agent(client, "Agent A")
    agent_b = create_agent(client, "Agent B", model=MODEL_B)
    room = create_room(client, [agent_a["id"], agent_b["id"]])

    posted = client.post(
        f"{BASE}/{room['id']}/messages",
        json={
            "content": "A hãy đề xuất kiến trúc, B hãy phản biện đề xuất của A",
            "mention_agent_ids": [agent_a["id"], agent_b["id"]],
        },
    )
    assert posted.status_code == 201, posted.text
    user_msg, reply_a, reply_b = posted.json()["messages"]
    assert "ARCH-RESULT-739" in reply_a["content"]
    assert "ARCH-RESULT-739" in prompts["b"]  # B really received A's result
    assert "Tôi thấy ARCH-RESULT-739" in reply_b["content"]
    assert reply_a["id"] in reply_b["context_message_ids"]
    assert reply_b["reply_to_message_id"] == user_msg["id"]
    assert reply_b["sequence"] > reply_a["sequence"] > user_msg["sequence"]


async def test_reply_to_targets_a_specific_message(owner, mock_agent):
    client, _ = owner
    prompts = []

    def handler(request):
        import json

        body = json.loads(request.content)
        prompts.append(body["messages"][-1]["content"])
        return httpx.Response(200, text=sse(chunk("Câu trả lời mẫu để phản biện"), "[DONE]"))

    mock_agent(handler)
    agent_a = create_agent(client, "Agent A")
    agent_b = create_agent(client, "Agent B")
    room = create_room(client, [agent_a["id"], agent_b["id"]])

    first = client.post(
        f"{BASE}/{room['id']}/messages",
        json={"content": "A nói trước đi", "mention_agent_ids": [agent_a["id"]]},
    )
    reply_a = first.json()["messages"][1]

    second = client.post(
        f"{BASE}/{room['id']}/messages",
        json={
            "content": "B hãy phản biện ý của A",
            "mention_agent_ids": [agent_b["id"]],
            "reply_to_message_id": reply_a["id"],
        },
    )
    assert second.status_code == 201, second.text
    reply_b = second.json()["messages"][1]
    assert reply_b["reply_to_message_id"] == reply_a["id"]
    assert "cần trả lời trực tiếp" in prompts[-1]
    assert "Câu trả lời mẫu để phản biện" in prompts[-1]

    from uuid import uuid4

    bad = client.post(
        f"{BASE}/{room['id']}/messages",
        json={"content": "Trả lời tin không có", "reply_to_message_id": str(uuid4())},
    )
    assert bad.status_code == 404
    assert bad.json()["detail"]["code"] == "collab_message_not_found"


async def test_long_room_transcript_still_answers(owner, mock_agent):
    """Regression: a roomy transcript (~12k chars of Vietnamese) blew
    past the Agent Studio default 8000-byte budget and every mention
    failed with agent_budget_exceeded; the room budget fits it."""
    client, _ = owner
    agent = create_agent(client)
    room = create_room(client, [agent["id"]])
    filler = "Nội dung thảo luận chi tiết về kiến trúc hệ thống. " * 40
    for index in range(7):
        posted = client.post(
            f"{BASE}/{room['id']}/messages",
            json={"content": f"Ý {index}: {filler}", "mention_agent_ids": []},
        )
        assert posted.status_code == 201, posted.text

    posted = client.post(
        f"{BASE}/{room['id']}/messages",
        json={"content": "Tổng hợp giúp tôi", "mention_agent_ids": [agent["id"]]},
    )
    assert posted.status_code == 201, posted.text
    reply = posted.json()["messages"][1]
    assert reply["status"] == "done"
    assert reply["content"] == "Xin chào từ Agent"


def create_room_full(client, payload):
    response = client.post(BASE, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def test_directed_post_records_run_and_tasks(owner, mock_agent):
    client, _ = owner
    agent = create_agent(client)
    room = create_room(client, [agent["id"]])
    posted = client.post(
        f"{BASE}/{room['id']}/messages",
        json={"content": "Làm việc A đi", "mention_agent_ids": [agent["id"]]},
    )
    assert posted.status_code == 201, posted.text
    body = posted.json()
    run = body["run"]
    assert run["mode"] == "directed"
    assert run["status"] == "completed"
    assert run["turn_count"] == 1
    assert body["messages"][0]["run_id"] == run["id"]
    assert body["messages"][1]["run_id"] == run["id"]

    detail = client.get(f"/api/v1/ai/collab/runs/{run['id']}")
    assert detail.status_code == 200, detail.text
    tasks = detail.json()["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["status"] == "completed"
    assert tasks[0]["assigned_by"] == "user"
    assert tasks[0]["output_message_id"] == body["messages"][1]["id"]

    runs = client.get(f"{BASE}/{room['id']}/runs").json()["runs"]
    assert [r["id"] for r in runs] == [run["id"]]


async def test_auto_mode_discusses_and_moderator_summarizes(owner, mock_agent, db, settings):
    client, owner_id = owner
    await seed(db, settings, owner_id, model_id=MODEL_B)
    prompts = []

    def handler(request):
        import json

        body = json.loads(request.content)
        prompt = body["messages"][-1]["content"]
        prompts.append(prompt)
        if "Moderator của phòng" in prompt:
            return httpx.Response(200, text=sse(chunk("Tổng hợp cuối cùng của phòng"), "[DONE]"))
        if body["model"] == MODEL_B:
            return httpx.Response(
                200, text=sse(chunk("[KẾT LUẬN] Đã đủ rõ, chốt phương án A"), "[DONE]")
            )
        return httpx.Response(200, text=sse(chunk("Phân tích kiến trúc ban đầu"), "[DONE]"))

    mock_agent(handler)
    architect = create_agent(client, "AI Architect")
    reviewer = create_agent(client, "AI Reviewer", model=MODEL_B)
    leader = create_agent(client, "AI Leader")
    room = create_room_full(
        client,
        {
            "title": "Phòng tự động",
            "agent_ids": [architect["id"], reviewer["id"], leader["id"]],
            "mode": "auto",
            "moderator_agent_id": leader["id"],
            "max_turns": 4,
        },
    )
    assert room["mode"] == "auto"
    assert room["moderator_agent_id"] == leader["id"]

    posted = client.post(
        f"{BASE}/{room['id']}/messages",
        json={"content": "Hãy bàn về kiến trúc hệ thống mới", "mention_agent_ids": []},
    )
    assert posted.status_code == 201, posted.text
    body = posted.json()
    run = body["run"]
    assert run["status"] == "completed"
    assert run["stop_reason"] == "agent_concluded"
    contents = [m["content"] for m in body["messages"]]
    assert "Phân tích kiến trúc ban đầu" in contents
    assert "Đủ rõ, chốt phương án A".lower() in " ".join(contents).lower()
    assert not any(c.startswith("[KẾT LUẬN]") for c in contents)  # marker stripped
    assert "Phân tích kiến trúc ban đầu" in prompts[1]  # Reviewer read Architect first
    summaries = [m for m in body["messages"] if m["is_summary"]]
    assert len(summaries) == 1
    assert summaries[0]["agent_name"] == "AI Leader"
    assert run["final_message_id"] == summaries[0]["id"]
    detail = client.get(f"/api/v1/ai/collab/runs/{run['id']}").json()
    assert [t["status"] for t in detail["tasks"]] == ["completed"] * 3
    assert detail["tasks"][2]["assigned_by"] == "moderator"


async def test_retry_failed_task(owner, mock_agent):
    client, _ = owner
    state = {"fail": True}

    def handler(request):
        if state["fail"]:
            return httpx.Response(500, text="boom")
        return httpx.Response(200, text=sse(chunk("Đã chạy lại thành công"), "[DONE]"))

    mock_agent(handler)
    agent = create_agent(client)
    room = create_room(client, [agent["id"]])
    posted = client.post(
        f"{BASE}/{room['id']}/messages",
        json={"content": "Thử việc khó", "mention_agent_ids": [agent["id"]]},
    )
    run = posted.json()["run"]
    assert run["status"] == "failed"
    assert run["stop_reason"] == "all_agents_failed"

    state["fail"] = False
    retried = client.post(f"/api/v1/ai/collab/runs/{run['id']}/retry")
    assert retried.status_code == 200, retried.text
    detail = retried.json()
    assert detail["run"]["status"] == "completed"
    assert detail["tasks"][0]["status"] == "completed"
    assert detail["tasks"][0]["attempt"] == 2
    messages = client.get(f"{BASE}/{room['id']}/messages").json()["messages"]
    assert messages[-1]["content"] == "Đã chạy lại thành công"

    again = client.post(f"/api/v1/ai/collab/runs/{run['id']}/retry")
    assert again.status_code == 422
    assert again.json()["detail"]["code"] == "collab_nothing_to_retry"

    missing = client.get("/api/v1/ai/collab/runs/00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "collab_run_not_found"


async def test_summarize_endpoint(owner, mock_agent):
    client, _ = owner
    agent = create_agent(client)
    room = create_room(client, [agent["id"]])
    client.post(f"{BASE}/{room['id']}/messages", json={"content": "Nội dung cần tổng hợp"})
    response = client.post(f"{BASE}/{room['id']}/summarize", json={})
    assert response.status_code == 201, response.text
    message = response.json()
    assert message["is_summary"] is True
    assert message["sender_type"] == "agent"
    assert message["content"] == "Xin chào từ Agent"

    empty = create_room(client, [])
    response = client.post(f"{BASE}/{empty['id']}/summarize", json={})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "collab_no_agents"


async def test_export_builds_report_json_and_zip(owner, mock_agent):
    import hashlib
    import io
    import zipfile

    client, _ = owner
    agent = create_agent(client)
    room = create_room(client, [agent["id"]])
    client.post(
        f"{BASE}/{room['id']}/messages",
        json={"content": "Hãy đề xuất kiến trúc", "mention_agent_ids": [agent["id"]]},
    )
    response = client.post(
        f"{BASE}/{room['id']}/export", json={"formats": ["md", "json", "zip"]}
    )
    assert response.status_code == 201, response.text
    artifacts = {a["kind"]: a for a in response.json()["artifacts"]}
    assert set(artifacts) == {"report", "transcript", "results", "package"}

    report = client.get(f"/api/v1/ai/collab/artifacts/{artifacts['report']['id']}/download")
    assert report.status_code == 200
    assert report.headers["content-disposition"].endswith('filename="FINAL-REPORT.md"')
    text = report.content.decode("utf-8")
    assert "Phòng dự án" in text
    assert hashlib.sha256(report.content).hexdigest() == artifacts["report"]["checksum"]
    assert artifacts["report"]["size"] == len(report.content)

    package = client.get(f"/api/v1/ai/collab/artifacts/{artifacts['package']['id']}/download")
    assert package.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(package.content))
    names = set(archive.namelist())
    assert {
        "README.md",
        "FINAL-REPORT.md",
        "discussion-transcript.md",
        "results.json",
        "manifest.json",
        "agent-results/agent-a.md",
    } <= names
    import json as jsonlib

    manifest = jsonlib.loads(archive.read("manifest.json"))
    for entry in manifest["files"]:
        data = archive.read(entry["name"])
        assert entry["size"] == len(data)
        assert entry["sha256"] == hashlib.sha256(data).hexdigest()
    transcript = archive.read("discussion-transcript.md").decode("utf-8")
    assert "Xin chào từ Agent" in transcript
    assert "api_key" not in archive.read("results.json").decode("utf-8").lower()

    listed = client.get(f"{BASE}/{room['id']}/artifacts").json()["artifacts"]
    assert len(listed) == 4
    assert client.delete(
        f"/api/v1/ai/collab/artifacts/{artifacts['results']['id']}"
    ).status_code == 204
    listed = client.get(f"{BASE}/{room['id']}/artifacts").json()["artifacts"]
    assert len(listed) == 3


async def test_artifacts_are_owner_scoped(owner, mock_agent, client_factory, register):
    client, _ = owner
    room = create_room(client, [])
    client.post(f"{BASE}/{room['id']}/messages", json={"content": "Ghi chú riêng"})
    created = client.post(f"{BASE}/{room['id']}/export", json={"formats": ["json"]})
    artifact_id = created.json()["artifacts"][0]["id"]

    stranger = client_factory()
    assert register(stranger, email="stranger9@example.com").status_code == 201
    assert (
        stranger.get(f"/api/v1/ai/collab/artifacts/{artifact_id}/download").status_code
        == 404
    )
    assert stranger.delete(f"/api/v1/ai/collab/artifacts/{artifact_id}").status_code == 404
    assert stranger.get(f"{BASE}/{room['id']}/artifacts").status_code == 404
