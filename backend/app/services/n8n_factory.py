"""MindFlow -> self-hosted n8n bridge behind the AI Factory page.

The page runs the n8n 7-agent workflow (workflow 07 in n8n-ai-factory/)
with the agents the user already created in MindFlow: for each team role
the user picks one of their own agents, and this service forwards that
agent's provider, model and system prompt to the n8n webhook. No agent is
created, copied or re-defined on the n8n side — the run configuration is
read from the caller's own agent records on every call.
"""

from uuid import UUID

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import Settings
from app.schemas.agents import AgentDetail
from app.schemas.n8n_factory import FACTORY_ROLES, FactoryRunOut, FactoryRunRequest
from app.services.agents import AgentService
from app.services.ai.base_provider import ProviderError

WEBHOOK_PATH = "/webhook/ai-team/start"


def build_team_payload(
    requirement: str, domain: list[str], agents_by_role: dict[str, AgentDetail]
) -> dict:
    """Build the workflow-07 webhook body (pure; unit-tested without I/O)."""
    return {
        "requirement": requirement,
        "domain": domain,
        "source": "mindflow",
        "agents": {
            role: {
                "name": agent.name,
                "provider": agent.provider,
                "model": agent.model,
                "system_prompt": agent.system_prompt or "",
            }
            for role, agent in agents_by_role.items()
        },
    }


class N8nHTTP:
    """Thin async client for the user's own n8n instance.

    The base URL comes from server settings only, never from the request,
    and no credentials are attached: the webhook is the entry point of the
    user's self-hosted n8n. Dependency-overridable in contract tests.
    """

    async def post_json(self, url: str, payload: dict, timeout_seconds: float) -> dict:
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout_seconds),
                follow_redirects=False,
                trust_env=False,
                headers={"Accept": "application/json"},
            ) as client:
                response = await client.post(url, json=payload)
        except (httpx.TimeoutException, httpx.RequestError):
            raise ProviderError("n8n_unreachable") from None
        if response.status_code >= 400:
            raise ProviderError("n8n_run_failed")
        try:
            data = response.json()
        except ValueError:
            raise ProviderError("n8n_run_failed") from None
        if not isinstance(data, dict):
            raise ProviderError("n8n_run_failed")
        return data


class N8nFactoryService:
    def __init__(self, db: AsyncIOMotorDatabase, settings: Settings, http: N8nHTTP):
        self.db = db
        self.settings = settings
        self.http = http

    async def run_team(self, user_id: UUID, payload: FactoryRunRequest) -> FactoryRunOut:
        unknown = [role for role in payload.assignments if role not in FACTORY_ROLES]
        if unknown:
            raise ProviderError("invalid_factory_roles")
        agents = AgentService(self.db, self.settings)
        by_role: dict[str, AgentDetail] = {}
        for role, agent_id in payload.assignments.items():
            # get_agent is owner-scoped: another user's agent id is a 404.
            by_role[role] = await agents.get_agent(user_id, agent_id)
        body = build_team_payload(payload.requirement, payload.domain, by_role)
        url = f"{self.settings.n8n_webhook_base_url}{WEBHOOK_PATH}"
        data = await self.http.post_json(
            url, body, self.settings.n8n_factory_timeout_seconds
        )
        return FactoryRunOut.model_validate(data)
