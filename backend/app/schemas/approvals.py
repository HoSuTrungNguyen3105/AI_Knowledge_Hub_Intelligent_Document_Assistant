from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

Decision = Literal["approved", "rejected", "changes_requested"]


class ApprovalOut(BaseModel):
    id: UUID
    workflow_id: UUID
    workflow_title: str
    kind: str = "workflow_completion"
    round: int = 1
    status: str  # pending|approved|rejected|changes_requested
    summary: str = ""
    comment: str | None = None
    created_at: datetime
    decided_at: datetime | None = None


class ApprovalList(BaseModel):
    approvals: list[ApprovalOut]


class DecideIn(BaseModel):
    decision: Decision
    comment: str | None = Field(default=None, max_length=4000)

    @field_validator("comment")
    @classmethod
    def strip_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class DecideOut(BaseModel):
    approval: ApprovalOut
    workflow_status: str | None = None
