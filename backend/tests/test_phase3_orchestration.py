"""NEXORA Phase 3 — parallel role tiers + Evaluator contract tests (offline).

Parallelism is proven by patching the resilient agent turn with an async
fake that records its own concurrency: two members of the same role tier
must overlap (max concurrency 2), while members of different tiers must not
(concurrency 1). The Evaluator tests run the real provider path against the
mock transport and distinguish the evaluation turn by the EVALUATION_RUBRIC
marker in its prompt.
"""

import asyncio
import json
from uuid import UUID

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from test_compare import MODEL_A, seed, sse, chunk

from app.api.v1.agents import agent_http
from app.services.ai.chat import ChatHTTP
from app.services.workflows import WorkflowService, effective_role, parse_evaluation

TEAMS = "/api/v1/ai/agent-teams"
WORKFLOWS = "/api/v1/ai/agent-workflows"

VERDICT_PASS = json.dumps(
    {"score": 88, "verdict": "pass", "summary": "Đạt yêu cầu", "issues": []}
)
VERDICT_REVISE = json.dumps(
    {
        "score": 40,
        "verdict": "revise",
        "summary": "Chưa đạt",
        "issues": ["Thiếu phần kiểm thử"],
    }
)


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


def make_agent(client, name, tools=None):
    r = client.post(
        "/api/v1/ai/agents",
        json={"name": name, "provider": "openai", "model": MODEL_A, "tools": tools or []},
    )
    assert r.status_code == 201, r.text
    return r.json()


def make_team(client, agents_roles, coordinator=None):
    members = [{"agent_id": a["id"], "role": role} for a, role in agents_roles]
    coord = coordinator or agents_roles[0][0]["id"]
    r = client.post(TEAMS, json={"name": "Team", "coordinator_agent_id": coord, "members": members})
    assert r.status_code == 201, r.text
    return r.json()


def make_workflow(client, team, goal="Build a login feature plan", **extra):
    r = client.post(WORKFLOWS, json={"team_id": team["id"], "title": "WF", "goal": goal, **extra})
    assert r.status_code == 201, r.text
    return r.json()


async def wait_done(client, workflow_id, timeout=15):
    for _ in range(int(timeout / 0.1)):
        wf = client.get(f"{WORKFLOWS}/{workflow_id}").json()
        if wf["status"] in ("completed", "failed", "cancelled", "waiting"):
            return wf
        await asyncio.sleep(0.1)
    raise AssertionError(f"workflow stuck: {wf}")


def get_events(client, workflow_id):
    return client.get(f"{WORKFLOWS}/{workflow_id}/events").json()["events"]


# --- Unit: verdict parsing + role inference ------------------------------------


def test_parse_evaluation_accepts_plain_and_wrapped_json():
    assert parse_evaluation(VERDICT_PASS)["score"] == 88
    wrapped = f"Here is my verdict:\n```json\n{VERDICT_PASS}\n```"
    parsed = parse_evaluation(wrapped)
    assert parsed["verdict"] == "pass" and parsed["issues"] == []


def test_parse_evaluation_defaults_verdict_from_score():
    low = parse_evaluation('{"score": 30, "summary": "weak"}')
    assert low["verdict"] == "revise"
    high = parse_evaluation('{"score": 95}')
    assert high["verdict"] == "pass"


def test_parse_evaluation_rejects_garbage():
    assert parse_evaluation("no json here") is None
    assert parse_evaluation('{"verdict": "pass"}') is None  # score is required
    assert parse_evaluation("") is None


def test_evaluator_role_inference_from_name():
    assert effective_role("member", "AI Evaluator") == "evaluator"
    assert effective_role("evaluator", "Anything") == "evaluator"


# --- Parallel tiers --------------------------------------------------------------


@pytest.fixture
def concurrency_probe(monkeypatch):
    state = {"active": 0, "max": 0}

    async def fake(self, user_id, agent_id, prompt, **kwargs):
        state["active"] += 1
        state["max"] = max(state["max"], state["active"])
        await asyncio.sleep(0.25)
        state["active"] -= 1
        return "Parallel result", {"input_tokens": 3, "output_tokens": 4}

    monkeypatch.setattr(WorkflowService, "_run_agent_resilient", fake)
    return state


async def test_same_tier_members_run_concurrently(owner, mock_http, concurrency_probe):
    client, _ = owner
    lead, dev1, dev2 = (make_agent(client, n) for n in ("Lead", "Dev One", "Dev Two"))
    team = make_team(
        client,
        [(lead, "coordinator"), (dev1, "developer"), (dev2, "developer")],
        coordinator=lead["id"],
    )
    wf = make_workflow(client, team)
    assert client.post(f"{WORKFLOWS}/{wf['id']}/start").status_code == 200
    done = await wait_done(client, wf["id"])
    assert done["status"] == "completed", done
    assert concurrency_probe["max"] >= 2, concurrency_probe
    tasks = client.get(f"{WORKFLOWS}/{wf['id']}/tasks").json()["tasks"]
    assert len(tasks) == 2 and all(t["status"] == "completed" for t in tasks)
    assert done["usage"]["agent_turns"] == 3  # 2 developers + coordinator synthesis


async def test_different_tiers_stay_sequential(owner, mock_http, concurrency_probe):
    client, _ = owner
    lead, planner, dev = (make_agent(client, n) for n in ("Lead", "Planner", "Dev"))
    team = make_team(
        client,
        [(lead, "coordinator"), (planner, "planner"), (dev, "developer")],
        coordinator=lead["id"],
    )
    wf = make_workflow(client, team)
    assert client.post(f"{WORKFLOWS}/{wf['id']}/start").status_code == 200
    done = await wait_done(client, wf["id"])
    assert done["status"] == "completed", done
    assert concurrency_probe["max"] == 1, concurrency_probe


# --- Evaluator -------------------------------------------------------------------


def verdict_handler(verdict_text):
    def handler(request, n):
        body = request.content.decode("utf-8", "ignore")
        if "EVALUATION_RUBRIC" in body:
            return httpx.Response(200, text=sse(chunk(verdict_text), "[DONE]"))
        return httpx.Response(200, text=sse(chunk("Done."), "[DONE]"))

    return handler


def make_eval_team(client):
    lead, dev, evaluator = (
        make_agent(client, n) for n in ("Lead", "Dev", "AI Evaluator")
    )
    return make_team(
        client,
        [(lead, "coordinator"), (dev, "developer"), (evaluator, "evaluator")],
        coordinator=lead["id"],
    )


async def test_evaluator_pass_records_score_event(owner, mock_http):
    client, _ = owner
    mock_http["configure"](verdict_handler(VERDICT_PASS))
    wf = make_workflow(client, make_eval_team(client))
    assert client.post(f"{WORKFLOWS}/{wf['id']}/start").status_code == 200
    done = await wait_done(client, wf["id"])
    assert done["status"] == "completed", done
    evaluations = [
        e for e in get_events(client, wf["id"]) if e["event_type"] == "evaluation_completed"
    ]
    assert len(evaluations) == 1
    assert evaluations[0]["payload"]["score"] == 88
    assert evaluations[0]["payload"]["verdict"] == "pass"


async def test_evaluator_revise_triggers_revision(owner, mock_http):
    client, _ = owner
    mock_http["configure"](verdict_handler(VERDICT_REVISE))
    wf = make_workflow(client, make_eval_team(client))
    assert client.post(f"{WORKFLOWS}/{wf['id']}/start").status_code == 200
    done = await wait_done(client, wf["id"])
    assert done["status"] == "completed", done
    evaluations = [
        e for e in get_events(client, wf["id"]) if e["event_type"] == "evaluation_completed"
    ]
    assert evaluations and evaluations[0]["payload"]["verdict"] == "revise"
    tasks = client.get(f"{WORKFLOWS}/{wf['id']}/tasks").json()["tasks"]
    dev_tasks = [t for t in tasks if t["title"].startswith("Developer")]
    assert dev_tasks and dev_tasks[0]["revision_count"] == 1


async def test_evaluator_unparsed_output_never_fails_workflow(owner, mock_http):
    client, _ = owner
    mock_http["configure"](verdict_handler("Tôi thấy khá ổn, không có gì để chê."))
    wf = make_workflow(client, make_eval_team(client))
    assert client.post(f"{WORKFLOWS}/{wf['id']}/start").status_code == 200
    done = await wait_done(client, wf["id"])
    assert done["status"] == "completed", done
    types = [e["event_type"] for e in get_events(client, wf["id"])]
    assert "evaluation_unparsed" in types and "evaluation_completed" not in types
