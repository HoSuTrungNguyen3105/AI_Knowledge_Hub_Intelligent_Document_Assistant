from io import StringIO
from pathlib import Path

import pytest
from alembic.config import Config
from conftest import TEST_SECRET
from pydantic import ValidationError
from sqlalchemy import delete, func, select

from alembic import command
from app.core.config import ROOT_ENV, Settings
from app.models import Base, Conversation, Document, KnowledgeBase, RefreshToken, User

BACKEND = Path(__file__).resolve().parents[1]


def test_health_queries_database_and_detects_missing_schema(client, db):
    assert client.get("/api/v1/health").json() == {"status": "ok"}
    Base.metadata.drop_all(db.bind)
    response = client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}
    assert "users" not in response.text


@pytest.mark.parametrize(
    "secret",
    ["short", "x" * 64, "change-me-to-a-long-random-secret-12345", "replace-with-secret" * 3],
)
def test_unsafe_secret_rejected(secret):
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(_env_file=None, jwt_secret=secret)


def test_secret_required(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_load_root_env_and_json_origins(monkeypatch, tmp_path):
    assert ROOT_ENV == BACKEND.parent / ".env"
    monkeypatch.delenv("JWT_SECRET", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        f'JWT_SECRET={TEST_SECRET}\nCORS_ORIGINS=["https://app.example.com"]\nCOOKIE_SECURE=true\n',
        encoding="utf-8",
    )
    settings = Settings(_env_file=env_file)
    assert settings.cors_origins == ["https://app.example.com"]
    assert settings.cookie_secure is True
    assert settings.database_url.startswith("postgresql+psycopg://")


@pytest.mark.parametrize("origin", ["*", "null", "http://localhost:3000/", "https://*.example.com"])
def test_settings_reject_non_origin_allowlist(origin):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, jwt_secret=TEST_SECRET, cors_origins=[origin])


def test_sqlite_cannot_be_selected_in_application_settings():
    with pytest.raises(ValidationError, match="postgresql"):
        Settings(_env_file=None, jwt_secret=TEST_SECRET, database_url="sqlite:///accidental.db")


def test_explicit_migration_compiles_to_postgresql_sql():
    output = StringIO()
    config = Config(str(BACKEND / "alembic.ini"), output_buffer=output)
    command.upgrade(config, "head", sql=True)
    sql = output.getvalue()
    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
    for table in Base.metadata.tables:
        assert f"CREATE TABLE {table}" in sql
    assert "TIMESTAMP WITH TIME ZONE" in sql
    assert "UUID" in sql
    assert "ON DELETE CASCADE" in sql
    assert "ON DELETE SET NULL" in sql
    assert "ck_documents_file_size_nonnegative" in sql
    assert "COMMIT" in sql
    output = StringIO()
    command.downgrade(
        Config(str(BACKEND / "alembic.ini"), output_buffer=output), "0001_phase_one:base", sql=True
    )
    assert "DROP TABLE users" in output.getvalue()
    assert "DROP EXTENSION" not in output.getvalue()


def test_foreign_key_deletion_policies(client, register, db):
    register(client)
    user = db.scalar(select(User))
    kb = KnowledgeBase(user_id=user.id, name="Knowledge")
    db.add(kb)
    db.flush()
    document = Document(
        user_id=user.id,
        knowledge_base_id=kb.id,
        original_filename="example.txt",
        file_size=1,
        mime_type="text/plain",
        storage_path="internal/example.txt",
    )
    conversation = Conversation(
        user_id=user.id, knowledge_base_id=kb.id, title="Chat", provider="openai", model="test"
    )
    db.add_all([document, conversation])
    db.commit()
    db.execute(delete(KnowledgeBase).where(KnowledgeBase.id == kb.id))
    db.commit()
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Document)) == 0
    assert db.get(Conversation, conversation.id).knowledge_base_id is None
    db.execute(delete(User).where(User.id == user.id))
    db.commit()
    assert db.scalar(select(func.count()).select_from(RefreshToken)) == 0
    assert db.scalar(select(func.count()).select_from(Conversation)) == 0
