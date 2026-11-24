"""Offline contracts for team recommendation + allocations
(mindflow-workforce-feature sections 4 + 6, wave 4).

The scoring expectations below are computed by hand from the documented
formula (skills 50 / workload 20 / availability 15 / cost 15, -25 type
mismatch) so a formula change breaks these tests loudly. Hard
constraints: an AI denied a task's scope and a disconnected AI are
excluded before scoring, and even a manual reassignment cannot put a
scope-barred AI back on the task.
"""

from uuid import UUID, uuid4

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


@pytest.fixture(autouse=True)
def encryption(settings):
    settings.credential_encryption_key = SecretStr(Fernet.generate_key().decode())


@pytest.fixture
async def owner(client, register, db, settings):
    assert register(client).status_code == 201
    owner_id = UUID(client.get("/api/v1/auth/me").json()["id"])
    await seed(db, settings, owner_id, price_in=0.000001, price_out=0.000002)
    return client


@pytest.fixture
def second(client_factory, register):
    client = client_factory()
    assert register(client, email="Second@Example.com", name="Second User").status_code == 201
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


@pytest.fixture
def roster(owner):
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
    ai_d = add_resource(owner, {
        "type": "ai", "name": "AI Offline", "role": "Coding Agent",
        "skills": [],
        "ai": {"provider": "groq", "model": "m"},
    })
    return {"a": human_a, "b": human_b, "c": ai_c, "d": ai_d}


@pytest.fixture
def analyzed_project(owner, mock_llm):
    response = owner.post(PROJECTS, json={
        "name": "Website thương mại điện tử",
        "description": "Website bán hàng Next.js có thanh toán và dashboard quản trị.",
        "tech_stack": ["Next.js", "PostgreSQL"],
    })
    assert response.status_code == 201, response.text
    project = response.json()
    response = owner.post(
        f"{PROJECTS}/{project['id']}/analyze",
        json={"provider": "openai", "model": MODEL_A},
    )
    assert response.status_code == 200, response.text
    return project


def recommend(owner, project_id):
    response = owner.post(f"{PROJECTS}/{project_id}/recommend", json={})
    assert response.status_code == 201, response.text
    return response.json()


def test_recommend_scoring_and_exclusions(owner, roster, analyzed_project):
    allocation = recommend(owner, analyzed_project["id"])
    assert allocation["status"] == "proposed"
    task0, task1 = allocation["items"]

    # Storefront: A 80 > C 62.5 > B 43 by the documented formula.
    assert [c["name"] for c in task0["candidates"]] == [
        "Nguyễn Văn A", "AI Frontend", "Trần Văn B",
    ]
    assert [c["score"] for c in task0["candidates"]] == [80, 62.5, 43]
    assert task0["resource_id"] == roster["a"]["id"]
    assert [e["name"] for e in task0["excluded"]] == ["AI Offline"]

    # Payment task: AI Frontend is barred by the payment-data hard
    # constraint, AI Offline is disconnected; A wins on availability.
    excluded = {e["name"]: e["reason"] for e in task1["excluded"]}
    assert "payment-data" in excluded["AI Frontend"]
    assert "AI Offline" in excluded
    assert task1["resource_id"] == roster["a"]["id"]
    assert task1["score"] == 35


def test_recommend_without_analysis(owner, roster):
    response = owner.post(PROJECTS, json={"name": "P", "description": "Chưa phân tích."})
    project = response.json()
    response = owner.post(f"{PROJECTS}/{project['id']}/recommend", json={})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "analysis_not_found"


def test_reassign_and_hard_constraint(owner, roster, analyzed_project):
    allocation = recommend(owner, analyzed_project["id"])
    url = f"{PROJECTS}/{analyzed_project['id']}/allocations/{allocation['id']}"

    response = owner.patch(
        url, json={"items": [{"task_index": 1, "resource_id": roster["b"]["id"]}]}
    )
    assert response.status_code == 200, response.text
    item = response.json()["items"][1]
    assert item["resource_id"] == roster["b"]["id"]
    assert item["score"] == 28

    # The scope-barred AI cannot be assigned even manually.
    response = owner.patch(
        url, json={"items": [{"task_index": 1, "resource_id": roster["c"]["id"]}]}
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "allocation_hard_constraint"

    # Unknown resource and unassignment.
    response = owner.patch(url, json={"items": [{"task_index": 0, "resource_id": str(uuid4())}]})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "resource_not_found"
    response = owner.patch(url, json={"items": [{"task_index": 0, "resource_id": None}]})
    assert response.status_code == 200
    assert response.json()["items"][0]["resource_id"] is None


def test_decide_approved(owner, roster, analyzed_project):
    allocation = recommend(owner, analyzed_project["id"])
    url = f"{PROJECTS}/{analyzed_project['id']}/allocations/{allocation['id']}"
    response = owner.post(f"{url}/decide", json={"decision": "approved"})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "approved"
    assert response.json()["decided_at"] is not None
    project = owner.get(f"{PROJECTS}/{analyzed_project['id']}").json()
    assert project["status"] == "approved"

    response = owner.post(f"{url}/decide", json={"decision": "rejected"})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "allocation_already_decided"
    response = owner.patch(url, json={"items": [{"task_index": 0, "resource_id": None}]})
    assert response.status_code == 422


def test_decide_rejected_keeps_project_analyzed(owner, roster, analyzed_project):
    allocation = recommend(owner, analyzed_project["id"])
    url = f"{PROJECTS}/{analyzed_project['id']}/allocations/{allocation['id']}"
    response = owner.post(f"{url}/decide", json={"decision": "rejected"})
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    project = owner.get(f"{PROJECTS}/{analyzed_project['id']}").json()
    assert project["status"] == "analyzed"


def test_allocation_owner_isolation(owner, second, roster, analyzed_project):
    allocation = recommend(owner, analyzed_project["id"])
    pid = analyzed_project["id"]
    assert second.post(f"{PROJECTS}/{pid}/recommend", json={}).status_code == 404
    assert second.get(f"{PROJECTS}/{pid}/allocations").status_code == 404
    url = f"{PROJECTS}/{pid}/allocations/{allocation['id']}"
    assert second.get(url).status_code == 404
    assert second.post(f"{url}/decide", json={"decision": "approved"}).status_code == 404
