import os
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.database import build_engine, build_session_factory, get_db
from app.models import Base

TEST_SECRET = "tests-only-1Qaz2Wsx3Edc4Rfv5Tgb6Yhn7Ujm8Ik"
ORIGIN = "http://localhost:3000"
PASSWORD = "a-test-password-123"
os.environ["JWT_SECRET"] = TEST_SECRET


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        jwt_secret=TEST_SECRET,
        database_url="postgresql+psycopg://test:test@127.0.0.1:5432/test",
        cors_origins=[ORIGIN, "http://127.0.0.1:3000"],
        cookie_secure=False,
        api_rate_limit=10_000,
        auth_rate_limit=10_000,
    )


@pytest.fixture
def session_factory(tmp_path):
    engine = build_engine(f"sqlite+pysqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    yield build_session_factory(engine)
    engine.dispose()


@pytest.fixture
def db(session_factory):
    with session_factory() as session:
        yield session
        session.rollback()


@pytest.fixture
def app(settings, session_factory):
    from app.main import create_app

    application = create_app(settings)

    def override_db():
        with session_factory() as session:
            try:
                yield session
            except Exception:
                session.rollback()
                raise

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
