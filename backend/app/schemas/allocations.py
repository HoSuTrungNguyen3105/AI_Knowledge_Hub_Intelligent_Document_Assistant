from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Team recommendation + allocations (mindflow-workforce-feature.md
# sections 2 + 4 + 6). An allocation is one recommendation run over one
# analysis: per task it stores the ranked candidates with their scores
# and reasons, the resources excluded by hard constraints, and the
# manager's current pick. Status: proposed -> approved | rejected.
ALLOCATION_STATUSES = ("proposed", "approved", "rejected")


class RecommendIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Omit to recommend from the project's latest analysis.
    analysis_id: UUID | None = None


class CandidateOut(BaseModel):
    resource_id: UUID
    name: str
    type: str
    score: float
    reason: str
    cost_per_hour: float | None = None


class ExcludedOut(BaseModel):
    resource_id: UUID
    name: str
    reason: str


class AllocationItemOut(BaseModel):
    task_index: int
    task_title: str
    task_skills: list[str]
    task_scopes: list[str]
    suggested_type: str
    resource_id: UUID | None = None
    resource_name: str | None = None
    resource_type: str | None = None
    score: float | None = None
    reason: str = ""
    candidates: list[CandidateOut]
    excluded: list[ExcludedOut]


class AllocationOut(BaseModel):
    id: UUID
    project_id: UUID
    analysis_id: UUID
    status: str
    items: list[AllocationItemOut]
    created_at: datetime
    updated_at: datetime
    decided_at: datetime | None = None


class AllocationList(BaseModel):
    allocations: list[AllocationOut]


class ReassignItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_index: int = Field(ge=0)
    resource_id: UUID | None = None  # null unassigns the task


class ReassignIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ReassignItem] = Field(min_length=1, max_length=30)


class DecideIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str

    @field_validator("decision")
    @classmethod
    def valid_decision(cls, value: str) -> str:
        decision = value.strip().lower()
        if decision not in ("approved", "rejected"):
            raise ValueError("Decision must be approved or rejected")
        return decision
