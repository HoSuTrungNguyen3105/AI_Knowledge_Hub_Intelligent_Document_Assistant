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
