import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Request
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import PyMongoError

from app.core.config import Settings

logger = logging.getLogger(__name__)


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
    await db.workspaces.create_index("owner_id")
    # Exactly one personal workspace per owner; team workspaces are exempt.
    await db.workspaces.create_index(
        [("owner_id", 1), ("kind", 1)],
        unique=True,
        partialFilterExpression={"kind": "personal"},
    )
    await db.workspace_members.create_index(
        [("workspace_id", 1), ("user_id", 1)], unique=True
    )
    await db.workspace_members.create_index("user_id")
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
    await db.seed_registry.create_index("key", unique=True)
    await db.collab_messages.create_index([("room_id", 1), ("created_at", 1)])
    await db.collab_messages.create_index([("user_id", 1), ("room_id", 1)])
    await db.resources.create_index([("user_id", 1), ("type", 1)])
    await db.resources.create_index([("user_id", 1), ("updated_at", -1)])
    await db.resources.create_index([("user_id", 1), ("skills.name", 1)])
    await db.projects.create_index([("user_id", 1), ("updated_at", -1)])
    await db.project_messages.create_index([("project_id", 1), ("created_at", 1)])
    await db.project_messages.create_index([("user_id", 1), ("project_id", 1)])
    await db.project_decisions.create_index([("project_id", 1), ("created_at", -1)])
    await db.project_decisions.create_index([("user_id", 1), ("project_id", 1)])
    await db.eval_datasets.create_index([("user_id", 1), ("updated_at", -1)])
    await db.eval_runs.create_index([("user_id", 1), ("created_at", -1)])
    await db.eval_runs.create_index([("user_id", 1), ("dataset_id", 1)])
    await db.eval_prompts.create_index([("user_id", 1), ("updated_at", -1)])
    await db.project_analyses.create_index([("project_id", 1), ("created_at", -1)])
    await db.project_analyses.create_index([("user_id", 1), ("project_id", 1)])
    await db.allocations.create_index([("project_id", 1), ("created_at", -1)])
    await db.allocations.create_index([("user_id", 1), ("project_id", 1)])
    await _drop_foreign_projects_index(db)


async def _drop_foreign_projects_index(db: AsyncIOMotorDatabase) -> None:
    """Drop the AI Agent Factory's unique index on ``projects.id``.

    The factory's Code Execution Service creates a unique index on the
    ``id`` field of its own ``projects`` collection at startup. When the
    CES is pointed at this database, that index lands on the Workforce
    ``projects`` collection instead. Workforce documents carry no ``id``
    field, MongoDB indexes a missing field as null, and a unique index
    then admits exactly one such document — every later project insert
    fails with DuplicateKeyError (surfaced as "Database unavailable").
    The index is foreign to this schema, so it is dropped whenever it
    is found; failures are logged, never raised.
    """
    try:
        info = await db.projects.index_information()
    except PyMongoError:
        logger.warning("Could not inspect projects indexes", exc_info=True)
        return
    for name, spec in info.items():
        keys = [tuple(pair) for pair in spec.get("key", [])]
        if keys == [("id", 1)] and spec.get("unique"):
            try:
                await db.projects.drop_index(name)
                logger.warning("Dropped foreign unique index %s on projects.id", name)
            except PyMongoError:
                logger.warning("Could not drop foreign index %s", name, exc_info=True)


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