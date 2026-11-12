from datetime import timedelta
from uuid import UUID

from conftest import PASSWORD

from app.models import ActivityLog, AIRequest, Conversation, Document, KnowledgeBase
from app.models.base import utcnow


def test_new_dashboard_has_real_zero_counts_and_registration_activity(client, register):
    register(client)
    response = client.get("/api/v1/dashboard")
    assert response.status_code == 200
    body = response.json()
    assert {key: value for key, value in body.items() if key != "recent_activity"} == {
        "total_documents": 0,
        "total_knowledge_bases": 0,
        "total_conversations": 0,
        "ai_requests_usage": 0,
    }
    assert len(body["recent_activity"]) == 1
    assert body["recent_activity"][0]["action"] == "auth.register"
    assert set(body["recent_activity"][0]) == {"id", "action", "description", "created_at"}
    assert response.headers["cache-control"] == "no-store"
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "person@example.com", "password": PASSWORD}
        ).status_code
        == 200
    )
    assert [
        item["action"] for item in client.get("/api/v1/dashboard").json()["recent_activity"]
    ] == ["auth.login", "auth.register"]


def test_seeded_dashboard_counts_and_activity_are_owner_isolated(
    client, client_factory, register, db
):
    owner = UUID(register(client).json()["user"]["id"])
    other_client = client_factory()
    other = UUID(register(other_client, email="other@example.com").json()["user"]["id"])
    for user_id, quantity in [(owner, 2), (other, 3)]:
        for number in range(quantity):
            kb = KnowledgeBase(
                id=KnowledgeBase.generate_id(),
                user_id=user_id,
                name=f"Knowledge {number}",
                description=None,
                created_at=utcnow(),
                updated_at=utcnow(),
            )
            await db.knowledge_bases.insert_one(kb.model_dump(by_alias=True))
            await db.documents.insert_one(
                Document(
                    id=Document.generate_id(),
                    user_id=user_id,
                    knowledge_base_id=kb.id,
                    original_filename=f"document-{number}.txt",
                    file_size=10,
                    mime_type="text/plain",
                    storage_path=f"internal/{user_id}/{number}.txt",
                    status="queued",
                    chunk_count=0,
                    error_message=None,
                    created_at=utcnow(),
                ).model_dump(by_alias=True)
            )
            await db.conversations.insert_one(
                Conversation(
                    id=Conversation.generate_id(),
                    user_id=user_id,
                    knowledge_base_id=kb.id,
                    title=f"Conversation {number}",
                    provider="openai",
                    model="test-model",
                    created_at=utcnow(),
                    updated_at=utcnow(),
                ).model_dump(by_alias=True)
            )
        for _ in range(quantity + 1):
            await db.ai_requests.insert_one(
                AIRequest(
                    id=AIRequest.generate_id(),
                    user_id=user_id,
                    provider="openai",
                    model="test-model",
                    status="completed",
                    created_at=utcnow(),
                ).model_dump(by_alias=True)
            )
    now = utcnow()
    activity_logs = []
    for number in range(12):
        activity_logs.append(
            ActivityLog(
                id=ActivityLog.generate_id(),
                user_id=owner,
                action="test.activity",
                description=f"Owner event {number}",
                created_at=now + timedelta(seconds=number),
            ).model_dump(by_alias=True)
        )
    activity_logs.append(
        ActivityLog(
            id=ActivityLog.generate_id(),
            user_id=other,
            action="test.private",
            description="Other user's secret",
            created_at=utcnow(),
        ).model_dump(by_alias=True)
    )
    await db.activity_logs.insert_many(activity_logs)
    owner_body = client.get("/api/v1/dashboard").json()
    other_body = other_client.get("/api/v1/dashboard").json()
    for key in ["total_documents", "total_knowledge_bases", "total_conversations"]:
        assert owner_body[key] == 2
        assert other_body[key] == 3
    assert owner_body["ai_requests_usage"] == 3
    assert other_body["ai_requests_usage"] == 4
    assert len(owner_body["recent_activity"]) == 10
    assert [item["description"] for item in owner_body["recent_activity"]] == [
        f"Owner event {number}" for number in range(11, 1, -1)
    ]
    assert "secret" not in str(owner_body)
    assert "Owner event" not in str(other_body)