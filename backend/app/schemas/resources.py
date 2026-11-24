from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Workforce resources (mindflow-workforce-feature.md sections 3 + 9): one
# collection holds both kinds of project resource, told apart by `type`.
# Shared fields (skills, availability, cost) sit at the top level so the
# recommendation scoring in a later wave can rank a single list; the
# type-specific detail sits in the `human` / `ai` block.
RESOURCE_TYPES = ("human", "ai")
HUMAN_AVAILABILITY = ("available", "busy", "unavailable")
AI_AVAILABILITY = ("connected", "disconnected")


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


class SkillIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    level: int = Field(ge=1, le=5)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        text = _strip(value)
        if not text:
            raise ValueError("Skill name cannot be empty")
        return text


class HumanProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experience_years: float | None = Field(default=None, ge=0, le=70)
    hours_per_week: int | None = Field(default=None, ge=0, le=80)
    current_project_count: int = Field(default=0, ge=0, le=100)


class AiProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str | None = Field(default=None, max_length=60)
    model: str | None = Field(default=None, max_length=160)
    runtime: str = Field(default="model-api", max_length=60)
    # Optional link to an existing MindFlow Agent owned by the caller; the
    # service validates ownership. Never an API key — keys stay in the
    # provider vault, per the spec's security note.
    agent_id: UUID | None = None
    allowed_tools: list[str] = Field(default_factory=list, max_length=30)
    denied_scopes: list[str] = Field(default_factory=list, max_length=30)
    token_limit_per_task: int | None = Field(default=None, gt=0)

    @field_validator("allowed_tools", "denied_scopes")
    @classmethod
    def clean_names(cls, values: list[str]) -> list[str]:
        return _clean_names(values)


class ResourceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    name: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=120)
    skills: list[SkillIn] = Field(default_factory=list, max_length=30)
    availability_status: str | None = None
    cost_per_hour: float | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=2000)
    human: HumanProfile | None = None
    ai: AiProfile | None = None

    @field_validator("type")
    @classmethod
    def valid_type(cls, value: str) -> str:
        kind = value.strip().lower()
        if kind not in RESOURCE_TYPES:
            raise ValueError("Type must be human or ai")
        return kind

    @field_validator("name", "role")
    @classmethod
    def valid_text(cls, value: str) -> str:
        text = _strip(value)
        if not text:
            raise ValueError("Value cannot be empty")
        return text

    @field_validator("skills")
    @classmethod
    def dedupe_skills(cls, values: list[SkillIn]) -> list[SkillIn]:
        seen: set[str] = set()
        unique: list[SkillIn] = []
        for skill in values:
            if skill.name.lower() not in seen:
                seen.add(skill.name.lower())
                unique.append(skill)
        return unique

    @model_validator(mode="after")
    def profile_matches_type(self):
        if self.type == "ai":
            if self.ai is None:
                raise ValueError("AI resources need an ai profile")
            if self.human is not None:
                raise ValueError("AI resources cannot carry a human profile")
            allowed, default = AI_AVAILABILITY, "disconnected"
        else:
            if self.human is None:
                self.human = HumanProfile()
            if self.ai is not None:
                raise ValueError("Human resources cannot carry an ai profile")
            allowed, default = HUMAN_AVAILABILITY, "available"
        if self.availability_status is None:
            self.availability_status = default
        elif self.availability_status not in allowed:
            raise ValueError("Availability status does not fit the resource type")
        return self


class ResourcePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # `type` is immutable: a person does not become an AI. The service
    # checks the profile blocks and availability against the stored type.
    name: str | None = Field(default=None, min_length=1, max_length=120)
    role: str | None = Field(default=None, min_length=1, max_length=120)
    skills: list[SkillIn] | None = Field(default=None, max_length=30)
    availability_status: str | None = None
    cost_per_hour: float | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=2000)
    human: HumanProfile | None = None
    ai: AiProfile | None = None

    @field_validator("name", "role")
    @classmethod
    def valid_text(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("Value cannot be null")
        text = _strip(value)
        if not text:
            raise ValueError("Value cannot be empty")
        return text

    @field_validator("skills")
    @classmethod
    def dedupe_skills(cls, values: list[SkillIn] | None) -> list[SkillIn] | None:
        if values is None:
            return None
        seen: set[str] = set()
        unique: list[SkillIn] = []
        for skill in values:
            if skill.name.lower() not in seen:
                seen.add(skill.name.lower())
                unique.append(skill)
        return unique


class ResourceOut(BaseModel):
    id: UUID
    type: str
    name: str
    role: str
    skills: list[SkillIn]
    availability_status: str
    cost_per_hour: float | None = None
    notes: str | None = None
    human: HumanProfile | None = None
    ai: AiProfile | None = None
    created_at: datetime
    updated_at: datetime


class ResourceList(BaseModel):
    resources: list[ResourceOut]
