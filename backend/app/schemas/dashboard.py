from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ActivityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    action: str
    description: str
    created_at: datetime


class DashboardResponse(BaseModel):
    total_documents: int
    total_knowledge_bases: int
    total_conversations: int
    ai_requests_usage: int
    recent_activity: list[ActivityResponse]
