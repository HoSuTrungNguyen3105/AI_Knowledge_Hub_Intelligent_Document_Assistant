from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _strip(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Must not be blank")
    return value


class RoomCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    agent_ids: list[UUID] = Field(default_factory=list, max_length=20)
    mode: str = Field(default="directed", pattern="^(directed|auto)$")
    moderator_agent_id: UUID | None = None
    max_turns: int = Field(default=4, ge=1, le=10)
    allow_handoff: bool = True

    @field_validator("title")
    @classmethod
    def valid_title(cls, value: str) -> str:
        return _strip(value)


class RoomPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=200)
    agent_ids: list[UUID] | None = Field(default=None, max_length=20)
    mode: str | None = Field(default=None, pattern="^(directed|auto)$")
    moderator_agent_id: UUID | None = None
    max_turns: int | None = Field(default=None, ge=1, le=10)
    allow_handoff: bool | None = None

    @field_validator("title")
    @classmethod
    def valid_title(cls, value: str | None) -> str | None:
        return _strip(value) if value is not None else None


class RoomAgentOut(BaseModel):
    id: UUID
    name: str
    provider: str
    model: str


class RoomOut(BaseModel):
    id: UUID
    title: str
    agent_ids: list[UUID] = Field(default_factory=list)
    agents: list[RoomAgentOut] = Field(default_factory=list)
    mode: str = "directed"
    moderator_agent_id: UUID | None = None
    max_turns: int = 4
    allow_handoff: bool = True
    message_count: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    created_at: datetime
    updated_at: datetime


class RoomList(BaseModel):
    rooms: list[RoomOut]


class MessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=8000)
    mention_agent_ids: list[UUID] = Field(default_factory=list, max_length=3)
    reply_to_message_id: UUID | None = None

    @field_validator("content")
    @classmethod
    def valid_content(cls, value: str) -> str:
        return _strip(value)


class CollabMessageOut(BaseModel):
    id: UUID
    room_id: UUID
    sender_type: str  # user|agent
    agent_id: UUID | None = None
    agent_name: str | None = None
    provider: str | None = None
    model: str | None = None
    content: str
    mentions: list[str] = Field(default_factory=list)
    sequence: int = 0
    reply_to_message_id: UUID | None = None
    context_message_ids: list[str] = Field(default_factory=list)
    run_id: UUID | None = None
    is_summary: bool = False
    input_tokens: int | None = None
    output_tokens: int | None = None
    status: str = "done"  # done|error
    error_code: str | None = None
    created_at: datetime


class CollabMessageList(BaseModel):
    messages: list[CollabMessageOut]


class RunOut(BaseModel):
    id: UUID
    room_id: UUID
    trigger_message_id: UUID
    mode: str  # directed|auto
    status: str  # running|completed|failed|cancelled
    turn_count: int = 0
    max_turns: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    stop_reason: str | None = None
    final_message_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class TaskOut(BaseModel):
    id: UUID
    run_id: UUID
    room_id: UUID
    agent_id: UUID
    agent_name: str | None = None
    assigned_by: str  # user|orchestrator|moderator
    status: str  # queued|running|completed|failed|cancelled
    output_message_id: UUID | None = None
    error_code: str | None = None
    attempt: int = 1
    input_tokens: int | None = None
    output_tokens: int | None = None
    created_at: datetime
    updated_at: datetime


class RunDetail(BaseModel):
    run: RunOut
    tasks: list[TaskOut] = Field(default_factory=list)


class RunList(BaseModel):
    runs: list[RunOut]


class SummarizeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_id: UUID | None = None


class PostResult(BaseModel):
    messages: list[CollabMessageOut]
    run: RunOut | None = None


class ExportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    formats: list[str] = Field(default_factory=lambda: ["md", "json", "zip"], max_length=3)
    run_id: UUID | None = None

    @field_validator("formats")
    @classmethod
    def valid_formats(cls, value: list[str]) -> list[str]:
        allowed = {"md", "json", "zip"}
        cleaned = [item for item in dict.fromkeys(value) if item in allowed]
        if not cleaned:
            raise ValueError("At least one supported format is required")
        return cleaned


class ArtifactOut(BaseModel):
    id: UUID
    room_id: UUID
    run_id: UUID | None = None
    name: str
    kind: str  # report|transcript|results|package
    mime_type: str
    size: int
    checksum: str
    created_at: datetime


class ArtifactList(BaseModel):
    artifacts: list[ArtifactOut]


class ExportResult(BaseModel):
    artifacts: list[ArtifactOut]


class RoleUsageOut(BaseModel):
    role: str | None = None
    agent_id: UUID | None = None
    agent_name: str | None = None
    provider: str | None = None
    model: str | None = None
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float | None = None


class RunUsageOut(BaseModel):
    run_id: UUID
    mode: str = "directed"
    status: str = "completed"
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float | None = None


class RoomUsageOut(BaseModel):
    room_id: UUID
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    # Estimated from the user's own synced model prices; None when no
    # priced model was used. Never a provider invoice.
    estimated_cost: float | None = None
    unpriced_requests: int = 0
    by_role: list[RoleUsageOut] = Field(default_factory=list)
    by_run: list[RunUsageOut] = Field(default_factory=list)
