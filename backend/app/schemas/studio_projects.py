from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StudioFileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=300)
    content: str = Field(default="", max_length=1_000_000)


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    files: list[StudioFileIn] = Field(default_factory=list, max_length=200)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("Name cannot be empty")
        return text


class ProjectPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            raise ValueError("Name cannot be empty")
        return text


class ProjectOut(BaseModel):
    id: UUID
    name: str
    file_count: int
    total_bytes: int
    created_at: datetime
    updated_at: datetime


class ProjectList(BaseModel):
    projects: list[ProjectOut]


class FileMetaOut(BaseModel):
    path: str
    size: int
    updated_at: datetime


class FileTreeOut(BaseModel):
    files: list[FileMetaOut]


class FileContentOut(BaseModel):
    path: str
    content: str
    size: int
    updated_at: datetime


class FileUpsertIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(default="", max_length=1_000_000)


class RunCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_ids: list[UUID] = Field(min_length=1, max_length=8)
    instruction: str = Field(min_length=1, max_length=8000)

    @field_validator("instruction")
    @classmethod
    def validate_instruction(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("Instruction cannot be empty")
        return text


class ChangeOut(BaseModel):
    id: UUID
    run_id: UUID | None = None
    agent_id: UUID | None = None
    agent_name: str | None = None
    path: str
    action: str
    source: str
    created_at: datetime


class ChangeList(BaseModel):
    changes: list[ChangeOut]


class RunStepOut(BaseModel):
    agent_id: UUID
    agent_name: str
    status: str
    error_code: str | None = None
    summary: str = ""
    files_changed: list[str] = Field(default_factory=list)
    input_tokens: int | None = None
    output_tokens: int | None = None


class RunOut(BaseModel):
    id: UUID
    project_id: UUID
    instruction: str
    status: str
    steps: list[RunStepOut] = Field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    created_at: datetime
    finished_at: datetime | None = None


class RunListOut(BaseModel):
    runs: list[RunOut]
