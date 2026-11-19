"""Agent persistence contract tests over the offline MongoDB mock.

Repository-level coverage for agents, executions (embedded step trace) and the
tool-execution audit collection, including owner isolation and cascade deletes.
Service/API/SSE coverage is added alongside the AgentService implementation.
"""

from uuid import uuid4

import pytest

from app.models.entities import AgentStep, AgentToolCall
from app.repositories.agents import AgentRepository


@pytest.fixture
def repo(db):
    return AgentRepository(db)


def new_agent(repo, user_id, **overrides):
    values = {
        "name": "Calculator Agent",
        "description": "Does math.",
        "system_prompt": "Be precise.",
        "provider": "groq",
        "model": "test-model",
        "temperature": 0.2,
        "max_output_tokens": 256,
        "tools": ["calculator"],
    }
    values.update(overrides)
    return repo.create_agent(user_id, **values)


async def test_agent_crud_and_owner_isolation(repo):
    user, other = uuid4(), uuid4()
    agent = await new_agent(repo, user)
    assert agent.tools == ["calculator"]
    assert agent.provider == "groq"

    fetched = await repo.get_agent(user, agent.id)
    assert fetched is not None and fetched.id == agent.id
    assert await repo.get_agent(other, agent.id) is None
    assert [a.id for a in await repo.list_agents(user)] == [agent.id]
    assert await repo.list_agents(other) == []

    updated = await repo.update_agent(
        user, agent.id, {"name": "Renamed", "tools": ["calculator", "datetime"]}
    )
    assert updated.name == "Renamed"
    assert updated.tools == ["calculator", "datetime"]
    # BSON persists milliseconds; compare persisted timestamps, not microseconds.
    assert updated.updated_at >= fetched.updated_at
    assert await repo.update_agent(other, agent.id, {"name": "x"}) is None

    assert await repo.delete_agent(other, agent.id) is False
    assert await repo.delete_agent(user, agent.id) is True
    assert await repo.get_agent(user, agent.id) is None


async def test_execution_lifecycle_with_embedded_steps(repo):
    user, other = uuid4(), uuid4()
    agent = await new_agent(repo, user)
    execution = await repo.create_execution(user, agent.id, prompt="What is 2+2?")
    assert execution.status == "running"
    assert execution.steps == []

    step = AgentStep(
        index=0,
        content="Let me calculate.",
        tool_calls=[
            AgentToolCall(
                id="call_1",
                name="calculator",
                arguments={"expression": "2+2"},
                status="success",
                result={"result": 4},
                latency_ms=3,
            )
        ],
        input_tokens=10,
        output_tokens=5,
    )
    await repo.append_step(user, execution.id, step)
    await repo.update_execution(
        user,
        execution.id,
        {
            "status": "success",
            "content": "2+2 = 4.",
            "input_tokens": 12,
            "output_tokens": 8,
            "latency_ms": 40,
            "estimated_cost": 0.0001,
        },
    )

    fetched = await repo.get_execution(user, execution.id)
    assert fetched.status == "success"
    assert fetched.content == "2+2 = 4."
    assert len(fetched.steps) == 1
    assert fetched.steps[0].tool_calls[0].result == {"result": 4}
    assert fetched.estimated_cost == 0.0001
    assert await repo.get_execution(other, execution.id) is None
    assert [e.id for e in await repo.list_executions(user, agent.id)] == [execution.id]
    assert await repo.list_executions(other, agent.id) == []


async def test_tool_execution_audit_and_owner_isolation(repo):
    user, other = uuid4(), uuid4()
    agent = await new_agent(repo, user)
    execution = await repo.create_execution(user, agent.id, prompt="hi")
    record = await repo.record_tool_execution(
        user,
        agent.id,
        execution.id,
        step_index=0,
        tool_name="calculator",
        arguments={"expression": "1+1"},
        result={"result": 2},
        status="success",
        error_code=None,
        latency_ms=2,
    )
    assert record.tool_name == "calculator"
    listed = await repo.list_tool_executions(user, execution.id)
    assert [t.id for t in listed] == [record.id]
    assert await repo.list_tool_executions(other, execution.id) == []


async def test_delete_execution_cascades_tool_audit(repo):
    user = uuid4()
    agent = await new_agent(repo, user)
    execution = await repo.create_execution(user, agent.id, prompt="hi")
    await repo.record_tool_execution(
        user, agent.id, execution.id, step_index=0, tool_name="calculator",
        arguments={}, result={"result": 0}, status="success", error_code=None, latency_ms=1,
    )
    assert await repo.delete_execution(user, execution.id) is True
    assert await repo.get_execution(user, execution.id) is None
    assert await repo.list_tool_executions(user, execution.id) == []
    assert await repo.delete_execution(user, execution.id) is False


async def test_delete_agent_cascades_executions_and_tool_audit(repo):
    user = uuid4()
    agent = await new_agent(repo, user)
    execution = await repo.create_execution(user, agent.id, prompt="hi")
    await repo.record_tool_execution(
        user, agent.id, execution.id, step_index=0, tool_name="datetime",
        arguments={"operation": "now"}, result={"iso": "x"}, status="success",
        error_code=None, latency_ms=1,
    )
    assert await repo.delete_agent(user, agent.id) is True
    assert await repo.list_executions(user, agent.id) == []
    assert await repo.list_tool_executions(user, execution.id) == []