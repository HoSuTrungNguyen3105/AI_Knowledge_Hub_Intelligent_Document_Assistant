from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.base import BaseDocument


class User(BaseDocument, BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    email: str
    name: str
    password_hash: str
    created_at: datetime


class RefreshToken(BaseDocument, BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    user_id: UUID
    token_hash: str
    expires_at: datetime
    revoked_at: datetime | None = None
    created_at: datetime


class KnowledgeBase(BaseDocument, BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    user_id: UUID
    name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class Document(BaseDocument, BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    user_id: UUID
    knowledge_base_id: UUID
    original_filename: str
    file_size: int
    mime_type: str
    storage_path: str
    status: str = "queued"
    chunk_count: int = 0
    error_message: str | None = None
    created_at: datetime


class Conversation(BaseDocument, BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    user_id: UUID
    knowledge_base_id: UUID | None = None
    title: str
    provider: str
    model: str
    system_prompt: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    created_at: datetime
    updated_at: datetime


class Message(BaseDocument, BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    conversation_id: UUID
    user_id: UUID
    role: str
    content: str
    status: str = "success"
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    error_code: str | None = None
    created_at: datetime


class AIRequest(BaseDocument, BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    user_id: UUID
    provider: str
    model: str
    status: str
    conversation_id: UUID | None = None
    message_id: UUID | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    created_at: datetime


class ActivityLog(BaseDocument, BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    user_id: UUID
    action: str
    description: str
    created_at: datetime