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

    @field_validator("title")
    @classmethod
    def valid_title(cls, value: str) -> str:
        return _strip(value)


class RoomPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=200)
    agent_ids: list[UUID] | None = Field(default=None, max_length=20)

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
    input_tokens: int | None = None
    output_tokens: int | None = None
    status: str = "done"  # done|error
    error_code: str | None = None
    created_at: datetime


class CollabMessageList(BaseModel):
    messages: list[CollabMessageOut]


class PostResult(BaseModel):
    messages: list[CollabMessageOut]
