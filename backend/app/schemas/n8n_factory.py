from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Canonical role names of the n8n 7-agent workflow
# (n8n-ai-factory/workflows/07-seven-agent-dynamic-routing.json). The bridge
# keys the forwarded agent configuration by these names.
FACTORY_ROLES = (
    "AI Leader",
    "AI Planner",
    "AI Architect",
    "AI Developer",
    "AI Tester",
    "AI Reviewer",
    "AI Researcher",
)

# Run lifecycle: queued -> running -> a terminal status. Terminal statuses
# mirror workflow 07's final-package `status` values; "failed" also covers
# runs that never produced a package (webhook rejected, or no callback
# arrived before the run timeout).
RUN_ACTIVE_STATUSES = ("queued", "running")
RUN_TERMINAL_STATUSES = (
    "completed",
    "completed_with_issues",
    "needs_configuration",
    "failed",
)


class FactoryRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement: str = Field(min_length=1, max_length=32000)
    domain: list[str] = Field(default_factory=list, max_length=8)
    # Role name -> agent id. Only the caller's own agents are accepted; the
    # service re-loads every agent owner-scoped before building the payload,
    # so a foreign agent id surfaces as agent_not_found, never as data.
    assignments: dict[str, UUID] = Field(default_factory=dict, max_length=7)

    @field_validator("requirement")
    @classmethod
    def validate_requirement(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("Requirement cannot be empty")
        return text

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item and item.strip()]
        if any(len(item) > 64 for item in cleaned):
            raise ValueError("Domain labels are limited to 64 characters")
        return cleaned


class FactoryAgentSnapshot(BaseModel):
    """One role assignment as captured when the run was created."""

    role: str
    agent_id: UUID
    name: str
    provider: str
    model: str


class FactoryRunOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    requirement: str
    domain: list[str] = Field(default_factory=list)
    assignments: list[FactoryAgentSnapshot] = Field(default_factory=list)
    status: str
    # Machine-readable failure detail (e.g. "n8n_unreachable",
    # "run_timed_out", or the finished package's own error text).
    error: str | None = None
    # The workflow-07 final package, stored verbatim once the run finishes.
    result: dict | None = None
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = None


class FactoryRunListOut(BaseModel):
    items: list[FactoryRunOut]
    total: int


class FactoryCallbackIn(BaseModel):
    """Body of the n8n -> MindFlow completion callback.

    The caller is authenticated by the run's own callback token in the
    Authorization header, not by a user session: n8n has no MindFlow
    session. The package is workflow 07's final package, stored verbatim.
    """

    model_config = ConfigDict(extra="forbid")

    package: dict
