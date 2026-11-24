"""Offline contracts for human approval gates (NEXORA Module 10).

State is arranged directly in the database (a workflow parked at the
gate in `waiting` + a pending approval), then decisions are exercised
through the service and the API: approve completes the workflow with
its stored result, reject fails it, request-changes feeds the comment
to the coordinator, double decisions are refused, and other users'
approvals are invisible.
"""

from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from app.models.base import utcnow
from app.schemas.approvals import DecideIn
from app.services.approvals import ApprovalsService

BASE = "/api/v1/ai/approvals"


@pytest.fixture(autouse=True)
def encryption(settings):
    settings.credential_encryption_key = SecretStr(Fernet.generate_key().decode())


@pytest.fixture
async def owner(client, register, db):
    assert register(client).status_code == 201
    owner_id = UUID(client.get("/api/v1/auth/me").json()["id"])
    return client, owner_id, db


async def _parked(db, owner_id: UUID, title="Workflow cần duyệt"):
    """A workflow waiting at the gate + its pending approval."""
    workflow_id = uuid4()
    now = utcnow()
    await db.agent_workflows.insert_one(
        {
            "_id": workflow_id,
            "user_id": owner_id,
            "team_id": uuid4(),
            "title": title,
            "goal": "Mục tiêu",
            "status": "waiting",
            "requires_approval": True,
            "approval_status": "pending",
            "final_result": "KẾT QUẢ CUỐI",
            "created_at": now,
            "updated_at": now,
        }
    )
    approval_id = uuid4()
    await db.approvals.insert_one(
        {
            "_id": approval_id,
            "user_id": owner_id,
            "workflow_id": workflow_id,
            "workflow_title": title,
            "kind": "workflow_completion",
            "round": 1,
            "status": "pending",
            "summary": "KẾT QUẢ CUỐI",
            "comment": None,
            "created_at": now,
            "decided_at": None,
        }
    )
    return workflow_id, approval_id


def test_approvals_require_auth(client):
    assert client.get(BASE).status_code == 401


async def test_inbox_lists_pending(owner):
    client, owner_id, db = owner
    await _parked(db, owner_id)
    body = client.get(BASE).json()
    assert len(body["approvals"]) == 1
    assert body["approvals"][0]["status"] == "pending"
    assert body["approvals"][0]["workflow_title"] == "Workflow cần duyệt"
    pending = client.get(BASE, params={"status": "pending"}).json()
    assert len(pending["approvals"]) == 1
    approved = client.get(BASE, params={"status": "approved"}).json()
    assert approved["approvals"] == []


async def test_approve_completes_workflow(owner):
    client, owner_id, db = owner
    workflow_id, approval_id = await _parked(db, owner_id)
    response = client.post(
        f"{BASE}/{approval_id}/decide", json={"decision": "approved", "comment": "Tốt"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["approval"]["status"] == "approved"
    assert body["approval"]["comment"] == "Tốt"
    assert body["workflow_status"] == "completed"

    workflow = await db.agent_workflows.find_one({"_id": workflow_id})
    assert workflow["status"] == "completed"
    assert workflow["approval_status"] == "approved"
    assert workflow["final_result"] == "KẾT QUẢ CUỐI"
    assert workflow["completed_at"] is not None

    log = await db.activity_logs.find_one({"user_id": owner_id, "action": "approval_decided"})
    assert log is not None
    note = await db.notifications.find_one({"user_id": owner_id, "kind": "approval_decided"})
    assert note is not None

    again = client.post(f"{BASE}/{approval_id}/decide", json={"decision": "approved"})
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "approval_already_decided"


async def test_reject_fails_workflow(owner):
    client, owner_id, db = owner
    workflow_id, approval_id = await _parked(db, owner_id)
    response = client.post(
        f"{BASE}/{approval_id}/decide", json={"decision": "rejected", "comment": "Chưa đạt"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["workflow_status"] == "failed"
    workflow = await db.agent_workflows.find_one({"_id": workflow_id})
    assert workflow["status"] == "failed"
    assert workflow["error_code"] == "approval_rejected"
    assert workflow["approval_status"] == "rejected"


async def test_request_changes_feeds_coordinator(owner):
    _, owner_id, db = owner
    workflow_id, approval_id = await _parked(db, owner_id)
    team_id = (await db.agent_workflows.find_one({"_id": workflow_id}))["team_id"]
    coordinator = uuid4()
    now = utcnow()
    await db.agent_teams.insert_one(
        {
            "_id": team_id,
            "user_id": owner_id,
            "name": "Nhóm",
            "description": "",
            "coordinator_agent_id": coordinator,
            "members": [],
            "created_at": now,
            "updated_at": now,
        }
    )
    result = await ApprovalsService(db).decide(
        owner_id, approval_id, DecideIn(decision="changes_requested", comment="Thêm phần giá")
    )
    assert result.workflow_status == "waiting"
    workflow = await db.agent_workflows.find_one({"_id": workflow_id})
    assert workflow["status"] == "waiting"
    assert workflow["approval_status"] == "changes_requested"
    message = await db.agent_messages.find_one(
        {"workflow_id": workflow_id, "message_type": "USER_REQUEST"}
    )
    assert message is not None
    assert message["content"] == "Thêm phần giá"
    assert message["to_agent_id"] == str(coordinator)


async def test_create_for_workflow_rounds(owner):
    _, owner_id, db = owner
    workflow_id, _ = await _parked(db, owner_id)
    workflow = await db.agent_workflows.find_one({"_id": workflow_id})

    class _W:
        id = workflow["_id"]
        title = workflow["title"]

    service = ApprovalsService(db)
    second = await service.create_for_workflow(owner_id, _W(), "Dài " * 6000)
    assert second.round == 2
    assert len(second.summary) == 20000
    note = await db.notifications.find_one({"user_id": owner_id, "kind": "approval_requested"})
    assert note is not None


async def test_approvals_are_owner_scoped(owner, client_factory, register):
    client, owner_id, db = owner
    _, approval_id = await _parked(db, owner_id)
    stranger = client_factory()
    assert register(stranger, email="stranger2@example.com").status_code == 201
    assert stranger.get(BASE).json()["approvals"] == []
    response = stranger.post(f"{BASE}/{approval_id}/decide", json={"decision": "approved"})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "approval_not_found"
    # The real owner's approval is untouched.
    mine = client.get(f"{BASE}/{approval_id}")
    assert mine.json()["status"] == "pending"
