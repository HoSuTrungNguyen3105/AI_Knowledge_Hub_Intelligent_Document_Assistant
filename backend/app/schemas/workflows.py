from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

ROLES = {
    "coordinator",
    "planner",
    "architect",
    "developer",
    "tester",
    "reviewer",
    "researcher",
    "evaluator",
    "member",
}
MESSAGE_TYPES = {
    "USER_REQUEST",
    "TASK_ASSIGNMENT",
    "MESSAGE",
    "QUESTION",
    "RESPONSE",
    "HANDOFF",
    "TASK_COMPLETED",
    "TASK_FAILED",
    "REVIEW_REQUEST",
    "REVISION_REQUEST",
    "APPROVAL",
    "WORKFLOW_UPDATE",
}


def _strip(value: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError("Value cannot be empty")
    return text


class TeamMemberIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_id: UUID
    role: str = "member"
    enabled: bool = True

    @field_validator("role")
    @classmethod
    def valid_role(cls, value: str) -> str:
        role = value.strip().lower()
        if role not in ROLES:
            raise ValueError("Invalid role")
        return role


class TeamCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    coordinator_agent_id: UUID
    members: list[TeamMemberIn] = Field(min_length=1, max_length=20)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        return _strip(value)


class TeamPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    coordinator_agent_id: UUID | None = None
    members: list[TeamMemberIn] | None = Field(default=None, min_length=1, max_length=20)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("Name cannot be null")
        return _strip(value)


class TeamMemberOut(BaseModel):
    agent_id: UUID
    role: str
    enabled: bool = True
    agent_name: str | None = None
    provider: str | None = None
    model: str | None = None


class TeamOut(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    coordinator_agent_id: UUID
    members: list[TeamMemberOut]
    created_at: datetime
    updated_at: datetime


class TeamList(BaseModel):
    teams: list[TeamOut]


OUTPUT_TYPES = {"text", "website_zip"}


class WorkflowCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    team_id: UUID
    title: str = Field(min_length=1, max_length=200)
    goal: str = Field(min_length=1, max_length=32000)
    max_steps: int | None = Field(default=None, ge=1, le=100)
    output_type: str = "text"
    design_brief: str | None = Field(default=None, max_length=1200)
    requires_approval: bool = False
    plan: dict | None = None

    @field_validator("title", "goal")
    @classmethod
    def valid_text(cls, value: str) -> str:
        return _strip(value)

    @field_validator("output_type")
    @classmethod
    def valid_output_type(cls, value: str) -> str:
        output_type = value.strip().lower()
        if output_type not in OUTPUT_TYPES:
            raise ValueError("Invalid output_type")
        return output_type


class WorkflowOut(BaseModel):
    id: UUID
    team_id: UUID
    title: str
    goal: str
    output_type: str = "text"
    design_brief: str | None = None
    plan: dict | None = None
    requires_approval: bool = False
    approval_status: str = "none"
    artifact_status: str = "none"
    artifact_file_count: int = 0
    artifact_total_bytes: int = 0
    artifact_error_code: str | None = None
    status: str
    current_step: int
    max_steps: int
    budget: dict = Field(default_factory=dict)
    usage: dict = Field(default_factory=dict)
    final_result: str | None = None
    error_code: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class WorkflowList(BaseModel):
    workflows: list[WorkflowOut]


class WorkflowFileOut(BaseModel):
    path: str
    size_bytes: int


class WorkflowFileList(BaseModel):
    files: list[WorkflowFileOut]
    total_bytes: int = 0
    artifact_status: str = "none"


class TaskOut(BaseModel):
    id: UUID
    workflow_id: UUID
    parent_task_id: UUID | None = None
    title: str
    description: str = ""
    assigned_agent_id: UUID | None = None
    created_by_agent_id: UUID | None = None
    depends_on: list[UUID] = Field(default_factory=list)
    status: str
    priority: str = "normal"
    result: str | None = None
    revision_count: int = 0
    created_at: datetime
    updated_at: datetime


class TaskList(BaseModel):
    tasks: list[TaskOut]


class MessageOut(BaseModel):
    id: UUID
    workflow_id: UUID
    task_id: UUID | None = None
    from_agent_id: str
    to_agent_id: str
    message_type: str
    content: str
    context_refs: list[str] = Field(default_factory=list)
    status: str
    created_at: datetime
    processed_at: datetime | None = None
    error_code: str | None = None


class MessageList(BaseModel):
    messages: list[MessageOut]


class EventOut(BaseModel):
    id: UUID
    workflow_id: UUID
    event_type: str
    actor_id: str | None = None
    payload: dict = Field(default_factory=dict)
    created_at: datetime


class EventList(BaseModel):
    events: list[EventOut]


# --- Dynamic planning (Task Analysis + Decomposition + Agent Selection) ------
# The Leader agent drafts a plan as JSON; PlanDraft validates it tolerantly
# (models return messy output — clamp and coerce instead of rejecting the
# whole plan, the same policy as the project analysis in schemas/projects).
# PlanOut is the backend-guaranteed shape the UI renders and PlanApplyIn
# echoes back: agent counts snapped to {1, 2, 3, 5}, dependency edges
# cycle-checked, waves computed, lineup matched against the user's real
# agents.

PLAN_COUNTS = (1, 2, 3, 5)
COMPLEXITIES = {"low", "medium", "high", "critical"}


def _clamp_text(value, limit):
    return str(value).strip()[:limit] if value is not None else value


def _clamp_list(value, limit, item_limit=200):
    if isinstance(value, str):
        return [value[:item_limit]]
    if isinstance(value, list):
        return [str(item)[:item_limit] for item in value][:limit]
    return value


class PlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: UUID  # the Leader agent performing the analysis
    title: str = Field(min_length=1, max_length=200)
    goal: str = Field(min_length=1, max_length=32000)
    mode: str = "auto"
    agent_count: int | None = None
    answers: str | None = Field(default=None, max_length=8000)

    @field_validator("title", "goal")
    @classmethod
    def valid_text(cls, value: str) -> str:
        return _strip(value)

    @field_validator("mode")
    @classmethod
    def valid_mode(cls, value: str) -> str:
        mode = value.strip().lower()
        if mode not in {"auto", "manual"}:
            raise ValueError("Invalid mode")
        return mode

    @field_validator("agent_count")
    @classmethod
    def valid_count(cls, value: int | None) -> int | None:
        if value is not None and value not in PLAN_COUNTS:
            raise ValueError("agent_count must be one of 1, 2, 3, 5")
        return value


class PlanTaskDraft(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str = ""
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    expected_output: str = Field(default="", max_length=1000)
    skills_required: list[str] = Field(default_factory=list, max_length=8)
    priority: str = "normal"
    difficulty: str = "medium"
    depends_on: list[str] = Field(default_factory=list, max_length=11)
    suggested_role: str = "member"
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("title", mode="before")
    @classmethod
    def clamp_title(cls, value):
        return _clamp_text(value, 200)

    @field_validator("description", mode="before")
    @classmethod
    def clamp_description(cls, value):
        return _clamp_text(value, 2000) or ""

    @field_validator("expected_output", mode="before")
    @classmethod
    def clamp_expected(cls, value):
        return _clamp_text(value, 1000) or ""

    @field_validator("skills_required", "acceptance_criteria", mode="before")
    @classmethod
    def clamp_lists(cls, value):
        return _clamp_list(value, 8, 120)

    @field_validator("depends_on", mode="before")
    @classmethod
    def clamp_deps(cls, value):
        return _clamp_list(value, 11, 40)

    @field_validator("priority")
    @classmethod
    def valid_priority(cls, value: str) -> str:
        priority = str(value).strip().lower()
        return priority if priority in {"low", "normal", "high"} else "normal"

    @field_validator("difficulty")
    @classmethod
    def valid_difficulty(cls, value: str) -> str:
        difficulty = str(value).strip().lower()
        return difficulty if difficulty in {"low", "medium", "high"} else "medium"

    @field_validator("suggested_role")
    @classmethod
    def valid_role(cls, value: str) -> str:
        role = str(value).strip().lower()
        return role if role in ROLES else "member"


class PlanDraft(BaseModel):
    model_config = ConfigDict(extra="ignore")

    summary: str = Field(min_length=1, max_length=2000)
    complexity: str = "medium"
    skills_required: list[str] = Field(default_factory=list, max_length=12)
    assumptions: list[str] = Field(default_factory=list, max_length=10)
    missing_info: list[str] = Field(default_factory=list, max_length=10)
    clarifying_questions: list[str] = Field(default_factory=list, max_length=5)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=10)
    recommended_agent_count: int = 1
    count_reason: str = Field(default="", max_length=1000)
    tasks: list[PlanTaskDraft] = Field(min_length=1, max_length=12)

    @field_validator("summary", mode="before")
    @classmethod
    def clamp_summary(cls, value):
        return _clamp_text(value, 2000)

    @field_validator("count_reason", mode="before")
    @classmethod
    def clamp_reason(cls, value):
        return _clamp_text(value, 1000) or ""

    @field_validator(
        "skills_required", "assumptions", "missing_info",
        "clarifying_questions", "acceptance_criteria",
        mode="before",
    )
    @classmethod
    def clamp_lists(cls, value):
        return _clamp_list(value, 12, 300)

    @field_validator("tasks", mode="before")
    @classmethod
    def clamp_tasks(cls, value):
        if isinstance(value, dict):
            return list(value.values())[:12]
        if isinstance(value, list):
            return value[:12]
        return value

    @field_validator("complexity")
    @classmethod
    def valid_complexity(cls, value: str) -> str:
        complexity = str(value).strip().lower()
        return complexity if complexity in COMPLEXITIES else "medium"


class PlanTaskOut(BaseModel):
    key: str
    title: str
    description: str = ""
    expected_output: str = ""
    skills_required: list[str] = Field(default_factory=list)
    priority: str = "normal"
    difficulty: str = "medium"
    depends_on: list[str] = Field(default_factory=list)
    parallelizable: bool = False
    wave: int = 0
    suggested_role: str = "member"
    acceptance_criteria: list[str] = Field(default_factory=list)


class PlanLineupItem(BaseModel):
    role: str
    agent_id: UUID | None = None
    agent_name: str | None = None
    provider: str | None = None
    model: str | None = None
    task_keys: list[str] = Field(default_factory=list)


class PlanHumanSuggestion(BaseModel):
    task_key: str
    resource_id: str
    name: str
    role: str | None = None
    score: float


class PlanOut(BaseModel):
    title: str
    goal: str
    summary: str
    complexity: str
    skills_required: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)
    clarifying_questions: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    mode: str
    recommended_agent_count: int
    chosen_agent_count: int
    count_reason: str = ""
    warnings: list[str] = Field(default_factory=list)
    tasks: list[PlanTaskOut]
    lineup: list[PlanLineupItem] = Field(default_factory=list)
    human_suggestions: list[PlanHumanSuggestion] = Field(default_factory=list)
    leader_agent_id: UUID
    input_tokens: int | None = None
    output_tokens: int | None = None


class PlanApplyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: PlanOut
    team_name: str | None = Field(default=None, max_length=120)
    output_type: str = "text"
    requires_approval: bool = False

    @field_validator("output_type")
    @classmethod
    def valid_output_type(cls, value: str) -> str:
        output_type = value.strip().lower()
        if output_type not in OUTPUT_TYPES:
            raise ValueError("Invalid output_type")
        return output_type


class PlanApplyOut(BaseModel):
    team: TeamOut
    workflow: WorkflowOut
