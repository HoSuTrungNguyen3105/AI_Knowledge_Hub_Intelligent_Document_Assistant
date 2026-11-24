from datetime import date, datetime
import re
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Workforce projects + AI analysis (mindflow-workforce-feature.md
# sections 2 + 9). A project carries the raw requirements; an analysis is
# one LLM pass that breaks it into tasks. The draft schema below is what
# the model's JSON is validated against before anything is stored — the
# spec is explicit that LLM output is never written unvalidated.
PROJECT_STATUSES = ("draft", "analyzed", "approved", "in_progress", "done", "archived")
SUGGESTED_TYPES = ("human", "ai", "either")


def _strip(value: str) -> str:
    return value.strip()


def _clean_names(values: list[str]) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for value in values:
        text = value.strip()
        if text and text.lower() not in seen:
            seen.add(text.lower())
            cleaned.append(text)
    return cleaned


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=10000)
    tech_stack: list[str] = Field(default_factory=list, max_length=30)
    deadline: date | None = None

    @field_validator("name", "description")
    @classmethod
    def valid_text(cls, value: str) -> str:
        text = _strip(value)
        if not text:
            raise ValueError("Value cannot be empty")
        return text

    @field_validator("tech_stack")
    @classmethod
    def clean_stack(cls, values: list[str]) -> list[str]:
        return _clean_names(values)


class ProjectPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, min_length=1, max_length=10000)
    tech_stack: list[str] | None = Field(default=None, max_length=30)
    deadline: date | None = None
    status: str | None = None

    @field_validator("name", "description")
    @classmethod
    def valid_text(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("Value cannot be null")
        text = _strip(value)
        if not text:
            raise ValueError("Value cannot be empty")
        return text

    @field_validator("tech_stack")
    @classmethod
    def clean_stack(cls, values: list[str] | None) -> list[str] | None:
        return None if values is None else _clean_names(values)

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("Status cannot be null")
        status = value.strip().lower()
        if status not in PROJECT_STATUSES:
            raise ValueError("Unknown project status")
        return status


class ProjectOut(BaseModel):
    id: UUID
    name: str
    description: str
    tech_stack: list[str]
    deadline: date | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class ProjectList(BaseModel):
    projects: list[ProjectOut]


class AnalyzeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=60)
    model: str = Field(min_length=1, max_length=160)


class AnalysisTask(BaseModel):
    # Parsed from LLM output: unknown keys are ignored on purpose (models
    # add prose fields), but the shape we rely on is strictly typed.
    model_config = ConfigDict(extra="ignore")

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    skills_required: list[str] = Field(default_factory=list, max_length=15)
    # Sensitive areas a task touches (e.g. "payment-data"); wave 4 matches
    # these against AI resources' denied_scopes as a hard constraint.
    scopes: list[str] = Field(default_factory=list, max_length=10)
    estimated_hours: float | None = Field(default=None, ge=0)
    suggested_type: str = "either"

    @field_validator("title", mode="before")
    @classmethod
    def clamp_title(cls, value):
        # Models happily emit over-long titles; clamp instead of
        # rejecting the whole analysis over a cosmetic field.
        return str(value).strip()[:200] if value is not None else value

    @field_validator("description", mode="before")
    @classmethod
    def clamp_description(cls, value):
        return str(value)[:2000] if value is not None else value

    @field_validator("skills_required", "scopes", mode="before")
    @classmethod
    def coerce_name_list(cls, value):
        # Models sometimes return "React, Node.js" instead of a list.
        if isinstance(value, str):
            return [part for part in (p.strip() for p in value.split(",")) if part]
        if isinstance(value, list):
            return [str(item)[:60] for item in value]
        return value

    @field_validator("estimated_hours", mode="before")
    @classmethod
    def coerce_hours(cls, value):
        # "8", "8 giờ", "khoảng 8-10 giờ" -> first number wins; no
        # number at all -> None (unknown) instead of a failed analysis.
        if isinstance(value, str):
            match = re.search(r"\d+(?:[.,]\d+)?", value)
            return float(match.group(0).replace(",", ".")) if match else None
        return value

    @field_validator("skills_required", "scopes")
    @classmethod
    def clean_names(cls, values: list[str]) -> list[str]:
        return _clean_names([str(value) for value in values])

    @field_validator("suggested_type")
    @classmethod
    def valid_suggested_type(cls, value: str) -> str:
        kind = str(value).strip().lower()
        return kind if kind in SUGGESTED_TYPES else "either"


class AnalysisDraft(BaseModel):
    model_config = ConfigDict(extra="ignore")

    summary: str = Field(min_length=1, max_length=4000)
    tasks: list[AnalysisTask] = Field(min_length=1, max_length=30)
    risks: list[str] = Field(default_factory=list, max_length=15)

    @field_validator("summary", mode="before")
    @classmethod
    def clamp_summary(cls, value):
        return str(value).strip()[:4000] if value is not None else value

    @field_validator("tasks", mode="before")
    @classmethod
    def coerce_tasks(cls, value):
        # A dict of tasks or an over-long list should not sink the
        # whole analysis; take the tasks in order, capped at 30.
        if isinstance(value, dict):
            return list(value.values())[:30]
        if isinstance(value, list):
            return value[:30]
        return value

    @field_validator("risks", mode="before")
    @classmethod
    def coerce_risks(cls, value):
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [str(item)[:300] for item in value][:15]
        return value


class AnalysisOut(BaseModel):
    id: UUID
    project_id: UUID
    provider: str
    model: str
    summary: str
    tasks: list[AnalysisTask]
    risks: list[str]
    total_estimated_hours: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    created_at: datetime


class AnalysisList(BaseModel):
    analyses: list[AnalysisOut]
