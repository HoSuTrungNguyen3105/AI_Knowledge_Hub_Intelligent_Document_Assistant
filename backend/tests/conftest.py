import os
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import Settings
from app.core.database import build_mongo_client, get_database, init_indexes
from app.main import create_app

TEST_SECRET = "tests-only-1Qaz2Wsx3Edc4Rfv5Tgb6Yhn7Ujm8Ik"
ORIGIN = "http://localhost:3000"
PASSWORD = "a-test-password-123"
os.environ["JWT_SECRET"] = TEST_SECRET


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        jwt_secret=TEST_SECRET,
        mongodb_uri="mongodb://localhost:27017",
        mongodb_database="mindflow_ai_test",
        cors_origins=[ORIGIN, "http://127.0.0.1:3000"],
        cookie_secure=False,
        api_rate_limit=10_000,
        auth_rate_limit=10_000,
    )


@pytest.fixture
async def mongo_client(settings):
    client = build_mongo_client(settings)
    try:
        await client.admin.command("ping")
        yield client
    except Exception:
        # Mock client if MongoDB not available
        client = AsyncMock(spec=AsyncIOMotorClient)
        yield client
    finally:
        if hasattr(client, "close"):
            client.close()


@pytest.fixture
async def db(mongo_client, settings):
    if isinstance(mongo_client, AsyncMock):
        yield AsyncMock(spec=AsyncIOMotorDatabase)
    else:
        database = get_database(mongo_client, settings)
        await init_indexes(database)
        yield database
        # Clean up test database
        await mongo_client.drop_database(settings.mongodb_database)


@pytest.fixture
def app(settings, db):
    application = create_app(settings)

    async def override_db():
        yield db

    application.dependency_overrides[get_db] = override_db
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client_factory(app):
    with ExitStack() as stack:

        def create(**kwargs):
            return stack.enter_context(TestClient(app, headers={"Origin": ORIGIN}, **kwargs))

        yield create


@pytest.fixture
def client(client_factory):
    return client_factory()


@pytest.fixture
def register():
    def create(client, email="Person@Example.com", name="  Test Person  ", password=PASSWORD):
        return client.post(
            "/api/v1/auth/register",
            json={"name": name, "email": email, "password": password},
        )

    return create