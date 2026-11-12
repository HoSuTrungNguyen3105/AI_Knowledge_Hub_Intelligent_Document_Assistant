from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DEFAULT_TITLE = "Phép so sánh mới"
MIN_TARGETS = 2
MAX_TARGETS = 4


class ComparisonTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=512)


class ComparisonCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=32000)
    targets: list[ComparisonTarget] = Field(min_length=MIN_TARGETS, max_length=MAX_TARGETS)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    system_prompt: str | None = Field(default=None, max_length=8000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_output_tokens: int | None = Field(default=None, ge=1, le=8192)

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("Prompt cannot be empty")
        return text

    @model_validator(mode="after")
    def validate_targets(self) -> Self:
        pairs = [(t.provider, t.model) for t in self.targets]
        if len(set(pairs)) != len(pairs):
            raise ValueError("Targets must be distinct provider/model pairs")
        return self


class SynthesizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=512)


class RunBrief(BaseModel):
    provider: str
    model: str
    status: str


class ComparisonRunOut(BaseModel):
    id: UUID
    provider: str
    model: str
    status: str
    content: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    error_code: str | None = None
    estimated_cost: float | None = None


class ComparisonSynthesisOut(BaseModel):
    provider: str
    model: str
    status: str
    content: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    error_code: str | None = None
    estimated_cost: float | None = None


class ComparisonSummary(BaseModel):
    id: UUID
    title: str
    targets: list[RunBrief]
    has_synthesis: bool
    created_at: datetime
    updated_at: datetime


class ComparisonDetail(ComparisonSummary):
    prompt: str
    system_prompt: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    runs: list[ComparisonRunOut]
    synthesis: ComparisonSynthesisOut | None = None


class ComparisonList(BaseModel):
    comparisons: list[ComparisonSummary]