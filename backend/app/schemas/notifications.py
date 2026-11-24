from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class NotificationOut(BaseModel):
    id: UUID
    kind: str
    title: str
    body: str = ""
    link: str | None = None
    read_at: datetime | None = None
    created_at: datetime


class NotificationList(BaseModel):
    notifications: list[NotificationOut]
    unread_count: int
