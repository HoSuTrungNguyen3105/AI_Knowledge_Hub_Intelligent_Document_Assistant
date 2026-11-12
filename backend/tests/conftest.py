"""In-memory MongoDB contract tests.

These run fully offline with mongomock-motor: no local MongoDB, no network and no
real credentials. They verify API/service/repository contracts, not BSON wire
behaviour. Real MongoDB integration is verified separately over HTTP (see README).
"""

import os
from contextlib import ExitStack, asynccontextmanager

import bson
import mongomock.collection as _mongomock_collection
import pytest
from bson.codec_options import CodecOptions
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.core.config import Settings
from app.core.database import get_database, get_db, init_indexes
from app.main import create_app

# mongomock validates inserts with bson's DEFAULT codec options, which reject
# native UUIDs (pymongo 4 "unspecified"). Production uses uuidRepresentation
# "standard"; align the offline validator so UUID/_id behaviour matches.
_STANDARD_CODEC = CodecOptions(uuid_representation=bson.binary.UuidRepresentation.STANDARD)
_REAL_BSON_ENCODE = bson.BSON.encode


class _StandardBSON:
    @staticmethod
    def encode(data, check_keys=False, codec_options=None):
        return _REAL_BSON_ENCODE(data, check_keys=check_keys, codec_options=_STANDARD_CODEC)


_mongomock_collection.BSON = _StandardBSON

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
def mongo_client():
    return AsyncMongoMockClient(tz_aware=True)


@pytest.fixture
async def db(mongo_client, settings):
    database = get_database(mongo_client, settings)
    await init_indexes(database)
    yield database
    await mongo_client.drop_database(settings.mongodb_database)


@pytest.fixture
def app(settings, db):
    application = create_app(settings)

    # The production lifespan opens a real MongoDB connection; tests inject the
    # in-memory database instead, so skip it to stay offline and deterministic.
    @asynccontextmanager
    async def _offline_lifespan(_app):
        yield

    application.router.lifespan_context = _offline_lifespan

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