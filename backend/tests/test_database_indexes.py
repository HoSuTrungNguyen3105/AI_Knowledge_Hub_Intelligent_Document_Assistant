"""The AI Agent Factory CES unique index on projects.id must not
survive in the MindFlow database: Workforce projects have no `id`
field, so the index would admit exactly one of them (incident
2026-11-24, project creation failed with "Database unavailable").
"""

import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.core.database import _drop_foreign_projects_index


async def _scenario() -> dict:
    client = AsyncMongoMockClient()
    db = client["mindflow_test"]
    # The foreign index, exactly as the CES creates it, plus our own.
    await db.projects.create_index([("id", 1)], unique=True)
    await db.projects.create_index([("user_id", 1), ("updated_at", -1)])
    await _drop_foreign_projects_index(db)
    return await db.projects.index_information()


def test_foreign_unique_id_index_is_dropped() -> None:
    info = asyncio.run(_scenario())
    assert "id_1" not in info
    # MindFlow's own projects index is untouched.
    assert "user_id_1_updated_at_-1" in info


def test_no_foreign_index_is_a_no_op() -> None:
    async def scenario() -> dict:
        client = AsyncMongoMockClient()
        db = client["mindflow_test"]
        await db.projects.create_index([("user_id", 1), ("updated_at", -1)])
        await _drop_foreign_projects_index(db)
        return await db.projects.index_information()

    info = asyncio.run(scenario())
    assert "user_id_1_updated_at_-1" in info
