from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# Roles a workspace member can hold (NEXORA spec Part 3, workspace scope).
# "owner" exists exactly once per workspace — the creator — and can never
# be assigned or changed through the member endpoints.
WORKSPACE_ROLES = ("owner", "admin", "leader", "employee", "operator", "viewer")
ASSIGNABLE_ROLES = ("admin", "leader", "employee", "operator", "viewer")


def _strip(value: str) -> str:
    return value.strip()


class WorkspaceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        text = _strip(value)
        if not text:
            raise ValueError("Name cannot be empty")
        return text


class WorkspacePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("Name cannot be null")
        text = _strip(value)
        if not text:
            raise ValueError("Name cannot be empty")
        return text


class MemberAdd(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=320)
    role: str = "employee"

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("role")
    @classmethod
    def valid_role(cls, value: str) -> str:
        role = value.strip().lower()
        if role not in ASSIGNABLE_ROLES:
            raise ValueError("Role cannot be owner and must be a workspace role")
        return role


class MemberPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str

    @field_validator("role")
    @classmethod
    def valid_role(cls, value: str) -> str:
        role = value.strip().lower()
        if role not in ASSIGNABLE_ROLES:
            raise ValueError("Role cannot be owner and must be a workspace role")
        return role


class WorkspaceOut(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    kind: str  # personal | team
    owner_id: UUID
    my_role: str
    member_count: int
    is_demo: bool = False
    created_at: datetime
    updated_at: datetime


class WorkspaceList(BaseModel):
    workspaces: list[WorkspaceOut]


class MemberOut(BaseModel):
    user_id: UUID
    email: str
    name: str
    role: str
    created_at: datetime


class MemberList(BaseModel):
    members: list[MemberOut]
