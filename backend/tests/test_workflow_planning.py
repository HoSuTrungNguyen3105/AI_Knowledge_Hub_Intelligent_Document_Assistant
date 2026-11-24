"""Dynamic planning tests (Task Analysis + Decomposition + Agent
Selection) for multi-agent workflows.

The Leader's plan comes from a mocked provider transport; everything
else — count snapping to {1,2,3,5}, manual-mode mismatch warnings,
dependency cycle handling, lineup matching against real agents, human
suggestions from Workforce resources, plan application, and the
orchestrator materializing plan tasks at runtime — runs for real.
"""

import asyncio
import json
from uuid import UUID

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from test_compare import MODEL_A, chunk, seed, sse

from app.api.v1.agents import agent_http
from app.services.ai.chat import ChatHTTP

TEAMS = "/api/v1/ai/agent-teams"
WORKFLOWS = "/api/v1/ai/agent-workflows"
PLAN = "/api/v1/ai/agent-workflows/plan"
RESOURCES = "/api/v1/ai/resources"


@pytest.fixture(autouse=True)
def encryption(settings):
    settings.credential_encryption_key = SecretStr(Fernet.generate_key().decode())


@pytest.fixture
def mock_http(app):
    state = {"handler": None, "calls": []}

    def make():
        def handler(request):
            state["calls"].append(request)
            if state["handler"]:
                return state["handler"](request, len(state["calls"]))
            return httpx.Response(200, text=sse(chunk("Done."), "[DONE]"))

        return ChatHTTP(transport=httpx.MockTransport(handler))

    app.dependency_overrides[agent_http] = make
    state["configure"] = lambda handler=None: state.update(handler=handler)
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


def plan_json(**overrides):
    doc = {
        "summary": "Kế hoạch mẫu",
        "complexity": "low",
        "skills_required": ["React"],
        "assumptions": [],
        "missing_info": [],
        "clarifying_questions": [],
        "acceptance_criteria": ["Chạy được"],
        "recommended_agent_count": 1,
        "count_reason": "Việc đơn giản, một chuyên môn.",
        "tasks": [
            {
                "key": "a", "title": "Làm giao diện", "description": "UI chính",
                "expected_output": "Trang hoàn chỉnh",
                "skills_required": ["React"], "priority": "normal",
                "difficulty": "low", "depends_on": [],
                "suggested_role": "developer", "acceptance_criteria": ["Đúng mockup"],
            }
        ],
    }
    doc.update(overrides)
    return json.dumps(doc)


def serve_plan(mock_http, text):
    def handler(request, _n):
        body = request.content.decode("utf-8", "ignore")
        if "PLAN_REQUEST" in body:
            return httpx.Response(200, text=sse(chunk(text), "[DONE]"))
        return httpx.Response(200, text=sse(chunk("Done."), "[DONE]"))

    mock_http["configure"](handler)


def request_plan(client, leader, **overrides):
    payload = {
        "agent_id": leader["id"],
        "title": "WF",
        "goal": "Xây trang bán hàng",
        "mode": "auto",
    }
    payload.update(overrides)
    r = client.post(PLAN, json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def test_plan_simple_task_proposes_one_agent(owner, mock_http):
    client, _ = owner
    leader = make_agent(client, "AI Leader")
    make_agent(client, "AI Developer")
    serve_plan(mock_http, plan_json())
    plan = request_plan(client, leader)
    assert plan["recommended_agent_count"] == 1
    assert plan["chosen_agent_count"] == 1
    assert plan["complexity"] == "low"
    assert len(plan["lineup"]) == 1
    assert plan["lineup"][0]["agent_name"] == "AI Developer"
    assert plan["lineup"][0]["task_keys"] == ["t1"]
    assert plan["tasks"][0]["key"] == "t1"
    assert plan["tasks"][0]["wave"] == 0


BUILD_REVIEW = plan_json(
    complexity="medium",
    recommended_agent_count=2,
    count_reason="Một Agent làm, một Agent review.",
    tasks=[
        {
            "key": "a", "title": "Viết API", "description": "Backend",
            "expected_output": "API xong", "skills_required": ["Node.js"],
            "priority": "high", "difficulty": "medium", "depends_on": [],
            "suggested_role": "developer", "acceptance_criteria": [],
        },
        {
            "key": "b", "title": "Review API", "description": "Kiểm tra chéo",
            "expected_output": "Báo cáo review", "skills_required": [],
            "priority": "normal", "difficulty": "low", "depends_on": ["a"],
            "suggested_role": "reviewer", "acceptance_criteria": [],
        },
    ],
)


def test_plan_manual_count_mismatch_warns(owner, mock_http):
    client, _ = owner
    leader = make_agent(client, "AI Leader")
    make_agent(client, "AI Developer")
    make_agent(client, "AI Reviewer")
    serve_plan(mock_http, BUILD_REVIEW)
    plan = request_plan(client, leader, mode="manual", agent_count=5)
    assert plan["recommended_agent_count"] == 2
    assert plan["chosen_agent_count"] == 5
    assert any("Bạn chọn 5 Agent" in warning for warning in plan["warnings"])
    task_b = [t for t in plan["tasks"] if t["key"] == "t2"][0]
    assert task_b["depends_on"] == ["t1"]
    assert task_b["wave"] == 1
    assert task_b["parallelizable"] is False


def test_plan_count_from_model_is_snapped(owner, mock_http):
    client, _ = owner
    leader = make_agent(client, "AI Leader")
    make_agent(client, "AI Developer")
    serve_plan(mock_http, plan_json(recommended_agent_count=4))
    plan = request_plan(client, leader)
    assert plan["recommended_agent_count"] == 3


def test_plan_cyclic_dependencies_are_dropped(owner, mock_http):
    client, _ = owner
    leader = make_agent(client, "AI Leader")
    make_agent(client, "AI Developer")
    cyclic = plan_json(tasks=[
        {
            "key": "a", "title": "Việc A", "description": "", "expected_output": "",
            "skills_required": [], "priority": "normal", "difficulty": "low",
            "depends_on": ["b"], "suggested_role": "developer",
            "acceptance_criteria": [],
        },
        {
            "key": "b", "title": "Việc B", "description": "", "expected_output": "",
            "skills_required": [], "priority": "normal", "difficulty": "low",
            "depends_on": ["a"], "suggested_role": "developer",
            "acceptance_criteria": [],
        },
    ])
    serve_plan(mock_http, cyclic)
    plan = request_plan(client, leader)
    by_key = {t["key"]: t for t in plan["tasks"]}
    assert by_key["t2"]["depends_on"] == []
    assert by_key["t1"]["depends_on"] == ["t2"]
    assert by_key["t2"]["wave"] == 0
    assert by_key["t1"]["wave"] == 1


def test_plan_invalid_model_output_fails_cleanly(owner, mock_http):
    client, _ = owner
    leader = make_agent(client, "AI Leader")
    serve_plan(mock_http, "không phải JSON")
    r = client.post(PLAN, json={
        "agent_id": leader["id"], "title": "WF", "goal": "Việc gì đó", "mode": "auto",
    })
    assert r.status_code == 502
    assert r.json()["detail"]["code"] == "analysis_invalid_response"


def test_plan_suggests_humans_from_workforce(owner, mock_http):
    client, _ = owner
    leader = make_agent(client, "AI Leader")
    make_agent(client, "AI Developer")
    created = client.post(RESOURCES, json={
        "type": "human", "name": "Chị Lan", "role": "Frontend Developer",
        "skills": [{"name": "React", "level": 5}],
        "human": {"experience_years": 5, "hours_per_week": 40, "current_project_count": 0},
    })
    assert created.status_code == 201
    serve_plan(mock_http, plan_json())
    plan = request_plan(client, leader)
    assert len(plan["human_suggestions"]) == 1
    suggestion = plan["human_suggestions"][0]
    assert suggestion["task_key"] == "t1"
    assert suggestion["name"] == "Chị Lan"
    assert suggestion["score"] == 100


async def wait_done(client, workflow_id, timeout=10):
    for _ in range(int(timeout / 0.1)):
        wf = client.get(f"{WORKFLOWS}/{workflow_id}").json()
        if wf["status"] in ("completed", "failed", "cancelled", "waiting"):
            return wf
        await asyncio.sleep(0.1)
    raise AssertionError(f"workflow stuck: {wf}")


async def test_apply_plan_and_run_materializes_plan_tasks(owner, mock_http):
    client, _ = owner
    leader = make_agent(client, "AI Leader")
    make_agent(client, "AI Developer")
    make_agent(client, "AI Reviewer")
    serve_plan(mock_http, BUILD_REVIEW)
    plan = request_plan(client, leader)
    r = client.post(f"{PLAN}/apply", json={"plan": plan})
    assert r.status_code == 201, r.text
    applied = r.json()
    workflow = applied["workflow"]
    assert workflow["plan"]["chosen_agent_count"] == 2
    assert "KẾ HOẠCH ĐÃ ĐƯỢC NGƯỜI DÙNG DUYỆT" in workflow["goal"]
    member_roles = {m["role"] for m in applied["team"]["members"]}
    assert member_roles == {"coordinator", "developer", "reviewer"}

    assert client.post(f"{WORKFLOWS}/{workflow['id']}/start").status_code == 200
    done = await wait_done(client, workflow["id"])
    assert done["status"] == "completed", done
    tasks = client.get(f"{WORKFLOWS}/{workflow['id']}/tasks").json()["tasks"]
    by_title = {t["title"]: t for t in tasks}
    assert "Viết API" in by_title
    assert "Review API" in by_title
    assert by_title["Review API"]["depends_on"] == [by_title["Viết API"]["id"]]
    assert "API xong" in by_title["Viết API"]["description"]
