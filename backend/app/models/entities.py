from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class User(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    email: str
    name: str
    password_hash: str
    created_at: datetime


class RefreshToken(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    user_id: UUID
    token_hash: str
    expires_at: datetime
    revoked_at: datetime | None = None
    created_at: datetime


class KnowledgeBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    user_id: UUID
    name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class Document(BaseModel):
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


class Conversation(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    user_id: UUID
    knowledge_base_id: UUID | None = None
    title: str
    provider: str
    model: str
    created_at: datetime
    updated_at: datetime


class AIRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    user_id: UUID
    provider: str
    model: str
    status: str
    created_at: datetime


class ActivityLog(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    user_id: UUID
    action: str
    description: str
    created_at: datetime