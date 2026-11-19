from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models import Agent, AgentExecution, ToolExecution
from app.models.base import utcnow
from app.models.entities import AgentStep


class AgentRepository:
    """Owner-scoped persistence for agents, their executions and tool audit.

    Executions embed the ordered step trace (read with the parent, like
    Comparison.runs). Tool executions are a separate audit collection so tool
    history can be queried across runs. Every filter is scoped by user_id.
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.agents = db.agents
        self.executions = db.agent_executions
        self.tool_executions = db.tool_executions

    # --- Agents ---
    async def create_agent(
        self,
        user_id: UUID,
        *,
        name: str,
        description: str | None,
        system_prompt: str | None,
        provider: str,
        model: str,
        temperature: float | None,
        max_output_tokens: int | None,
        tools: list[str],
    ) -> Agent:
        now = utcnow()
        doc = {
            "_id": Agent.generate_id(),
            "user_id": user_id,
            "name": name,
            "description": description,
            "system_prompt": system_prompt,
            "provider": provider,
            "model": model,
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
            "tools": tools,
            "created_at": now,
            "updated_at": now,
        }
        await self.agents.insert_one(doc)
        return Agent(**doc)

    async def list_agents(self, user_id: UUID) -> list[Agent]:
        cursor = self.agents.find({"user_id": user_id}).sort("updated_at", -1)
        return [Agent(**doc) async for doc in cursor]

    async def get_agent(self, user_id: UUID, agent_id: UUID) -> Agent | None:
        doc = await self.agents.find_one({"_id": agent_id, "user_id": user_id})
        return Agent(**doc) if doc else None

    async def update_agent(
        self, user_id: UUID, agent_id: UUID, values: dict
    ) -> Agent | None:
        doc = await self.agents.find_one_and_update(
            {"_id": agent_id, "user_id": user_id},
            {"$set": {**values, "updated_at": utcnow()}},
            return_document=True,
        )
        return Agent(**doc) if doc else None

    async def delete_agent(self, user_id: UUID, agent_id: UUID) -> bool:
        result = await self.agents.delete_one({"_id": agent_id, "user_id": user_id})
        if result.deleted_count == 0:
            return False
        # Cascade: drop the agent's executions and their tool audit records.
        await self.tool_executions.delete_many({"agent_id": agent_id, "user_id": user_id})
        await self.executions.delete_many({"agent_id": agent_id, "user_id": user_id})
        return True

    # --- Executions ---
    async def create_execution(
        self, user_id: UUID, agent_id: UUID, *, prompt: str,
        provider: str | None = None, model: str | None = None,
    ) -> AgentExecution:
        now = utcnow()
        doc = {
            "_id": AgentExecution.generate_id(),
            "agent_id": agent_id,
            "user_id": user_id,
            "provider": provider,
            "model": model,
            "prompt": prompt,
            "status": "running",
            "content": "",
            "steps": [],
            "input_tokens": None,
            "output_tokens": None,
            "latency_ms": None,
            "error_code": None,
            "estimated_cost": None,
            "created_at": now,
            "updated_at": now,
        }
        await self.executions.insert_one(doc)
        return AgentExecution(**doc)

    async def list_executions(self, user_id: UUID, agent_id: UUID) -> list[AgentExecution]:
        cursor = self.executions.find(
            {"user_id": user_id, "agent_id": agent_id}
        ).sort("created_at", -1)
        return [AgentExecution(**doc) async for doc in cursor]

    async def get_execution(self, user_id: UUID, execution_id: UUID) -> AgentExecution | None:
        doc = await self.executions.find_one({"_id": execution_id, "user_id": user_id})
        return AgentExecution(**doc) if doc else None

    async def append_step(self, user_id: UUID, execution_id: UUID, step: AgentStep) -> None:
        await self.executions.update_one(
            {"_id": execution_id, "user_id": user_id},
            {"$push": {"steps": step.model_dump()}, "$set": {"updated_at": utcnow()}},
        )

    async def update_execution(self, user_id: UUID, execution_id: UUID, values: dict) -> None:
        await self.executions.update_one(
            {"_id": execution_id, "user_id": user_id},
            {"$set": {**values, "updated_at": utcnow()}},
        )

    async def delete_execution(self, user_id: UUID, execution_id: UUID) -> bool:
        result = await self.executions.delete_one({"_id": execution_id, "user_id": user_id})
        if result.deleted_count == 0:
            return False
        await self.tool_executions.delete_many(
            {"execution_id": execution_id, "user_id": user_id}
        )
        return True

    # --- Tool audit ---
    async def record_tool_execution(
        self,
        user_id: UUID,
        agent_id: UUID,
        execution_id: UUID,
        *,
        step_index: int,
        tool_name: str,
        arguments: dict,
        result: dict | None,
        status: str,
        error_code: str | None,
        latency_ms: int | None,
    ) -> ToolExecution:
        doc = {
            "_id": ToolExecution.generate_id(),
            "execution_id": execution_id,
            "agent_id": agent_id,
            "user_id": user_id,
            "step_index": step_index,
            "tool_name": tool_name,
            "arguments": arguments,
            "result": result,
            "status": status,
            "error_code": error_code,
            "latency_ms": latency_ms,
            "created_at": utcnow(),
        }
        await self.tool_executions.insert_one(doc)
        return ToolExecution(**doc)

    async def list_tool_executions(
        self, user_id: UUID, execution_id: UUID
    ) -> list[ToolExecution]:
        cursor = self.tool_executions.find(
            {"user_id": user_id, "execution_id": execution_id}
        ).sort("created_at", 1)
        return [ToolExecution(**doc) async for doc in cursor]