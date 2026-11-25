"""Project Discussion schemas (Project_Discussion.md).

A discussion belongs to one project and one owner. Mentions carry real
Agent IDs chosen from the mention autocomplete — never names parsed out
of the text — so routing cannot be spoofed by typing a name. Decisions
keep a status history instead of being overwritten.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

DECISION_STATUSES = ("proposed", "approved", "rejected", "superseded")


def _strip(value: str) -> str:
    return value.strip()


class DiscussionMessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=8000)
    # Real agent IDs from the mention picker; capped like collab mentions.
    mention_agent_ids: list[UUID] = Field(default_factory=list, max_length=3)
    # @All: the router picks the suitable agents (at most 3).
    mention_all: bool = False

    @field_validator("content")
    @classmethod
    def valid_content(cls, value: str) -> str:
        return _strip(value)


class DiscussionMessageOut(BaseModel):
    id: UUID
    project_id: UUID
    sender_type: str  # "user" | "agent"
    agent_id: UUID | None = None
    agent_name: str | None = None
    content: str
    mentions: list[str] = []
    mention_all: bool = False
    in_reply_to: UUID | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    status: str = "done"  # "done" | "error"
    error_code: str | None = None
    converted_analysis_id: UUID | None = None
    converted_task_index: int | None = None
    created_at: datetime


class DiscussionList(BaseModel):
    messages: list[DiscussionMessageOut]


class DiscussionPostOut(BaseModel):
    messages: list[DiscussionMessageOut]


class DecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    reason: str = Field(default="", max_length=2000)
    source_message_id: UUID | None = None

    @field_validator("title", "reason")
    @classmethod
    def valid_text(cls, value: str) -> str:
        return _strip(value)


class DecisionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    reason: str | None = Field(default=None, max_length=2000)
    status: str | None = None
    # When approving, optionally mark an older approved decision as
    # superseded by this one (its history keeps the trail).
    supersedes_id: UUID | None = None

    @field_validator("title", "reason")
    @classmethod
    def valid_text(cls, value: str | None) -> str | None:
        return None if value is None else _strip(value)

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        status = value.strip().lower()
        if status not in DECISION_STATUSES:
            raise ValueError("Unknown decision status")
        return status


class DecisionStatusEntry(BaseModel):
    status: str
    at: datetime


class DecisionOut(BaseModel):
    id: UUID
    project_id: UUID
    title: str
    reason: str = ""
    status: str
    source_message_id: UUID | None = None
    status_history: list[DecisionStatusEntry] = []
    created_at: datetime
    updated_at: datetime


class DecisionList(BaseModel):
    decisions: list[DecisionOut]


class ConvertTaskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Empty fields fall back to the source message content.
    title: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=2000)
    acceptance_criteria: str = Field(default="", max_length=2000)
    skills_required: list[str] = Field(default_factory=list, max_length=15)
    scopes: list[str] = Field(default_factory=list, max_length=10)
    estimated_hours: float | None = Field(default=None, ge=0)
    suggested_type: str = "either"

    @field_validator("title", "description", "acceptance_criteria")
    @classmethod
    def valid_text(cls, value: str) -> str:
        return _strip(value)

    @field_validator("suggested_type")
    @classmethod
    def valid_suggested_type(cls, value: str) -> str:
        kind = str(value).strip().lower()
        return kind if kind in ("human", "ai", "either") else "either"


class ConvertTaskOut(BaseModel):
    analysis_id: UUID
    task_index: int
    task_title: str
