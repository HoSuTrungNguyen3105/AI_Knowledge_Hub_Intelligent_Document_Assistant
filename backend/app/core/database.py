from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Request
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import Settings


def build_mongo_client(settings: Settings) -> AsyncIOMotorClient:
    return AsyncIOMotorClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        socketTimeoutMS=30000,
        maxPoolSize=10,
        minPoolSize=1,
        uuidRepresentation="standard",
        tz_aware=True,
    )


def get_database(client: AsyncIOMotorClient, settings: Settings) -> AsyncIOMotorDatabase:
    return client[settings.mongodb_database]


async def init_indexes(db: AsyncIOMotorDatabase) -> None:
    await db.users.create_index("email", unique=True)
    await db.refresh_tokens.create_index("user_id")
    await db.refresh_tokens.create_index("token_hash", unique=True)
    await db.refresh_tokens.create_index("expires_at")
    await db.knowledge_bases.create_index("user_id")
    await db.documents.create_index("user_id")
    await db.documents.create_index("knowledge_base_id")
    await db.conversations.create_index("user_id")
    await db.conversations.create_index("knowledge_base_id")
    await db.conversations.create_index([("user_id", 1), ("updated_at", -1)])
    await db.conversations.create_index("multi_chat_id")
    await db.multi_chats.create_index([("user_id", 1), ("updated_at", -1)])
    await db.messages.create_index([("conversation_id", 1), ("created_at", 1)])
    await db.messages.create_index("user_id")
    await db.ai_requests.create_index("user_id")
    await db.activity_logs.create_index([("user_id", 1), ("created_at", -1)])
    await db.user_provider_credentials.create_index([("user_id", 1), ("provider", 1)], unique=True)
    await db.ai_models.create_index([("credential_id", 1), ("model_id", 1)], unique=True)
    await db.comparisons.create_index("user_id")
    await db.comparisons.create_index([("user_id", 1), ("updated_at", -1)])
    await db.agents.create_index("user_id")
    await db.agents.create_index([("user_id", 1), ("updated_at", -1)])
    await db.agent_executions.create_index([("user_id", 1), ("agent_id", 1), ("created_at", -1)])
    await db.agent_executions.create_index("agent_id")
    await db.tool_executions.create_index([("user_id", 1), ("execution_id", 1), ("created_at", 1)])
    await db.tool_executions.create_index("agent_id")
    await db.agent_teams.create_index([("user_id", 1), ("updated_at", -1)])
    await db.agent_workflows.create_index([("user_id", 1), ("created_at", -1)])
    await db.agent_workflows.create_index([("team_id", 1), ("status", 1)])
    await db.agent_tasks.create_index([("workflow_id", 1), ("status", 1)])
    await db.agent_tasks.create_index([("assigned_agent_id", 1), ("status", 1)])
    await db.agent_messages.create_index([("workflow_id", 1), ("created_at", 1)])
    await db.agent_messages.create_index([("to_agent_id", 1), ("status", 1)])
    await db.agent_workflow_events.create_index([("workflow_id", 1), ("created_at", 1)])
    await db.agent_workflow_files.create_index([("workflow_id", 1), ("path", 1)])
    await db.agent_workflow_files.create_index("user_id")


@asynccontextmanager
async def lifespan_mongo(settings: Settings) -> AsyncGenerator[AsyncIOMotorClient, None]:
    client = build_mongo_client(settings)
    try:
        await client.admin.command("ping")
        db = get_database(client, settings)
        await init_indexes(db)
        yield client
    finally:
        client.close()


async def get_db(request: Request) -> AsyncGenerator[AsyncIOMotorDatabase, None]:
    client: AsyncIOMotorClient = request.app.state.mongo_client
    db = get_database(client, request.app.state.settings)
    yield db