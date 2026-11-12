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
    await db.messages.create_index([("conversation_id", 1), ("created_at", 1)])
    await db.messages.create_index("user_id")
    await db.ai_requests.create_index("user_id")
    await db.activity_logs.create_index([("user_id", 1), ("created_at", -1)])
    await db.user_provider_credentials.create_index([("user_id", 1), ("provider", 1)], unique=True)
    await db.ai_models.create_index([("credential_id", 1), ("model_id", 1)], unique=True)


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