from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.dependencies import CurrentUser, Database
from app.schemas.notifications import NotificationList, NotificationOut
from app.services.notifications import NotificationsService

router = APIRouter(tags=["Notifications"])


@router.get("/ai/notifications", response_model=NotificationList)
async def list_notifications(
    user: CurrentUser,
    db: Database,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> NotificationList:
    """The caller's latest notifications plus the unread count."""
    return await NotificationsService(db).list(user.id, limit=limit)


@router.post("/ai/notifications/read-all", response_model=NotificationList)
async def mark_all_read(user: CurrentUser, db: Database) -> NotificationList:
    return await NotificationsService(db).mark_all_read(user.id)


@router.post("/ai/notifications/{notification_id}/read", response_model=NotificationOut)
async def mark_read(
    notification_id: UUID, user: CurrentUser, db: Database
) -> NotificationOut:
    return await NotificationsService(db).mark_read(user.id, notification_id)
