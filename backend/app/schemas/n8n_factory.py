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


class FactoryRunOut(BaseModel):
    # Mirrors the final package of n8n workflow 07. Extra fields pass through
    # so new workflow outputs reach the page without a backend change.
    model_config = ConfigDict(extra="allow")

    project_id: str | None = None
    status: str
    domain: list = Field(default_factory=list)
    plan: dict | None = None
    plan_error: str | None = None
    task_results: list[dict] = Field(default_factory=list)
    skipped_roles: list[dict] = Field(default_factory=list)
    review: dict | None = None
    final: dict | None = None
    agent_assignments: list[dict] = Field(default_factory=list)
    agent_assignments_ignored: list[dict] = Field(default_factory=list)
    duration_ms: int | None = None
