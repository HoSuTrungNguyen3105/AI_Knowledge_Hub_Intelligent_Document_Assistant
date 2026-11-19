from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    system_prompt: str | None = Field(default=None, max_length=8000)
    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=512)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_output_tokens: int | None = Field(default=None, ge=1, le=8192)
    tools: list[str] = Field(default_factory=list, max_length=16)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("Name cannot be empty")
        return text

    @field_validator("tools")
    @classmethod
    def dedupe_tools(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class AgentPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    system_prompt: str | None = Field(default=None, max_length=8000)
    provider: str | None = Field(default=None, min_length=1, max_length=64)
    model: str | None = Field(default=None, min_length=1, max_length=512)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_output_tokens: int | None = Field(default=None, ge=1, le=8192)
    tools: list[str] | None = Field(default=None, max_length=16)

    @field_validator("provider", "model", "tools")
    @classmethod
    def reject_null_required_fields(cls, value):
        if value is None:
            raise ValueError("Required agent fields cannot be null")
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("Name cannot be null")
        text = value.strip()
        if not text:
            raise ValueError("Name cannot be empty")
        return text

    @field_validator("tools")
    @classmethod
    def dedupe_tools(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else list(dict.fromkeys(value))


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=32000)

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("Prompt cannot be empty")
        return text


class AgentSummary(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    provider: str
    model: str
    tools: list[str]
    created_at: datetime
    updated_at: datetime


class AgentDetail(AgentSummary):
    system_prompt: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None


class AgentList(BaseModel):
    agents: list[AgentSummary]


class AgentToolCallOut(BaseModel):
    id: str
    name: str
    arguments: dict
    status: str
    result: dict | None = None
    error_code: str | None = None
    latency_ms: int | None = None


class AgentStepOut(BaseModel):
    index: int
    content: str
    tool_calls: list[AgentToolCallOut]
    input_tokens: int | None = None
    output_tokens: int | None = None


class ToolExecutionOut(BaseModel):
    id: UUID
    step_index: int
    tool_name: str
    arguments: dict
    result: dict | None = None
    status: str
    error_code: str | None = None
    latency_ms: int | None = None
    created_at: datetime


class ExecutionSummary(BaseModel):
    id: UUID
    agent_id: UUID
    provider: str | None = None
    model: str | None = None
    prompt: str
    status: str
    step_count: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost: float | None = None
    created_at: datetime
    updated_at: datetime


class ExecutionDetail(ExecutionSummary):
    content: str
    steps: list[AgentStepOut]
    latency_ms: int | None = None
    error_code: str | None = None
    tool_executions: list[ToolExecutionOut]


class ExecutionList(BaseModel):
    executions: list[ExecutionSummary]


class ToolCatalogItem(BaseModel):
    name: str
    description: str
    parameters: dict | None = None
    available: bool
    phase: int | None = None


class ToolCatalog(BaseModel):
    tools: list[ToolCatalogItem]