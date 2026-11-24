"""End-to-end flow test for the Projects feature: Project Analysis AI
-> team recommendation by capability score -> manager approval.

Where test_projects.py and test_allocations.py cover each step in
isolation, this file walks the exact journey the /projects page drives,
through the real HTTP API in order:

  create resources -> create project (draft) -> analyze (mocked LLM,
  streamed JSON) -> project "analyzed" -> recommend (deterministic
  scores, hard-constraint exclusion) -> manager reassigns one task ->
  approve -> project "approved"

A second scenario runs the same journey on top of the 50 seeded demo
employees, mirroring what the seed button on /workforce sets up.
"""

from uuid import UUID

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from test_compare import MODEL_A, chunk, seed, sse
from test_projects import ANALYSIS_JSON

from app.api.v1.agents import agent_http
from app.services.ai.chat import ChatHTTP

PROJECTS = "/api/v1/ai/projects"
RESOURCES = "/api/v1/ai/resources"
SEED = "/api/v1/ai/seed/workforce"


@pytest.fixture(autouse=True)
def encryption(settings):
    settings.credential_encryption_key = SecretStr(Fernet.generate_key().decode())
    settings.app_env = "development"


@pytest.fixture
async def owner(client, register, db, settings):
    assert register(client).status_code == 201
    owner_id = UUID(client.get("/api/v1/auth/me").json()["id"])
    await seed(db, settings, owner_id, price_in=0.000001, price_out=0.000002)
    return client


@pytest.fixture
def mock_llm(app):
    def handler(_request):
        return httpx.Response(
            200, text=sse(chunk(ANALYSIS_JSON[:25]), chunk(ANALYSIS_JSON[25:]), "[DONE]")
        )

    app.dependency_overrides[agent_http] = lambda: ChatHTTP(
        transport=httpx.MockTransport(handler)
    )


def add_resource(client, payload):
    response = client.post(RESOURCES, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def create_and_analyze(client):
    response = client.post(PROJECTS, json={
        "name": "Website thương mại điện tử",
        "description": "Website bán hàng Next.js có thanh toán và dashboard quản trị.",
        "tech_stack": ["Next.js", "PostgreSQL"],
    })
    assert response.status_code == 201, response.text
    project = response.json()
    assert project["status"] == "draft"
    response = client.post(
        f"{PROJECTS}/{project['id']}/analyze",
        json={"provider": "openai", "model": MODEL_A},
    )
    assert response.status_code == 200, response.text
    return project, response.json()


def test_full_project_flow(owner, mock_llm):
    # 1. The roster the recommendation will rank.
    human_a = add_resource(owner, {
        "type": "human", "name": "Nguyễn Văn A", "role": "Frontend Developer",
        "skills": [{"name": "React", "level": 5}, {"name": "Next.js", "level": 4}],
        "cost_per_hour": 20,
        "human": {"experience_years": 4, "hours_per_week": 40, "current_project_count": 0},
    })
    human_b = add_resource(owner, {
        "type": "human", "name": "Trần Văn B", "role": "Backend Developer",
        "skills": [{"name": "React", "level": 3}],
        "availability_status": "busy", "cost_per_hour": 10,
        "human": {"experience_years": 2, "hours_per_week": 40, "current_project_count": 3},
    })
    ai_c = add_resource(owner, {
        "type": "ai", "name": "AI Frontend", "role": "Coding Agent",
        "skills": [{"name": "React", "level": 4}],
        "availability_status": "connected",
        "ai": {"provider": "groq", "model": "m", "denied_scopes": ["payment-data"]},
    })
    add_resource(owner, {
        "type": "ai", "name": "AI Offline", "role": "Coding Agent",
        "skills": [],
        "ai": {"provider": "groq", "model": "m"},
    })

    # 2-3. Project + AI analysis.
    project, analysis = create_and_analyze(owner)
    assert len(analysis["tasks"]) == 2
    assert owner.get(f"{PROJECTS}/{project['id']}").json()["status"] == "analyzed"

    # 4. Recommendation: A wins both tasks; the payment task excludes
    # the scope-barred AI before scoring.
    response = owner.post(f"{PROJECTS}/{project['id']}/recommend", json={})
    assert response.status_code == 201, response.text
    allocation = response.json()
    assert allocation["status"] == "proposed"
    task0, task1 = allocation["items"]
    assert task0["resource_id"] == human_a["id"]
    assert task0["score"] == 80
    assert task1["resource_id"] == human_a["id"]
    assert ai_c["id"] in [entry["resource_id"] for entry in task1["excluded"]]

    # 5. The manager overrides the payment task to B.
    url = f"{PROJECTS}/{project['id']}/allocations/{allocation['id']}"
    response = owner.patch(
        url, json={"items": [{"task_index": 1, "resource_id": human_b["id"]}]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["items"][1]["resource_id"] == human_b["id"]

    # 6. Approval closes the journey: allocation decided, project approved.
    response = owner.post(f"{url}/decide", json={"decision": "approved"})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "approved"
    assert owner.get(f"{PROJECTS}/{project['id']}").json()["status"] == "approved"

    listed = owner.get(f"{PROJECTS}/{project['id']}/allocations").json()["allocations"]
    assert [item["id"] for item in listed] == [allocation["id"]]


def test_flow_with_seeded_employees(owner, mock_llm):
    # The /workforce seed button path: 50 demo employees, then the same
    # journey. Scores are not asserted (the roster is data, not a fixed
    # fixture) — the shape of the outcome is.
    response = owner.post(SEED)
    assert response.status_code == 200, response.text
    assert response.json()["created"] == 50

    project, _analysis = create_and_analyze(owner)
    response = owner.post(f"{PROJECTS}/{project['id']}/recommend", json={})
    assert response.status_code == 201, response.text
    allocation = response.json()
    assert len(allocation["items"]) == 2
    for item in allocation["items"]:
        assert len(item["candidates"]) >= 40  # most of the roster is eligible
        assert item["resource_id"] is not None
        assert item["score"] > 0
        assert item["reason"]

    url = f"{PROJECTS}/{project['id']}/allocations/{allocation['id']}"
    response = owner.post(f"{url}/decide", json={"decision": "approved"})
    assert response.status_code == 200
    assert owner.get(f"{PROJECTS}/{project['id']}").json()["status"] == "approved"


def test_flow_without_any_resources(owner, mock_llm):
    # Nobody to recommend: items stay unassigned with an explanation,
    # and the manager can still close the flow out.
    project, _analysis = create_and_analyze(owner)
    response = owner.post(f"{PROJECTS}/{project['id']}/recommend", json={})
    assert response.status_code == 201, response.text
    allocation = response.json()
    for item in allocation["items"]:
        assert item["resource_id"] is None
        assert item["candidates"] == []
        assert "Không có nguồn lực" in item["reason"]
