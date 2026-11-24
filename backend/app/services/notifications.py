"""In-app notifications (NEXORA Module 15, v1).

Notifications are *derived* records: domain services call :func:`notify`
when something the user should know about happens (a workflow finishes,
an AI Factory run completes, an approval is requested or decided). The
helper never raises — a failed notification must not break the workflow
that produced it — and the API layer below is strictly owner-scoped.
"""

import logging
from uuid import UUID, uuid4

from app.models.base import utcnow
from app.schemas.notifications import NotificationList, NotificationOut
from app.services.ai.base_provider import ProviderError

logger = logging.getLogger(__name__)

COLLECTION = "notifications"


async def notify(
    db,
    user_id: UUID,
    *,
    kind: str,
    title: str,
    body: str = "",
    link: str | None = None,
) -> None:
    """Best-effort notification insert used by other services."""
    try:
        await db[COLLECTION].insert_one(
            {
                "_id": uuid4(),
                "user_id": user_id,
                "kind": kind,
                "title": title,
                "body": body,
                "link": link,
                "read_at": None,
                "created_at": utcnow(),
            }
        )
    except Exception:  # pragma: no cover - notification must never break the flow
        logger.warning("Failed to store notification kind=%s", kind, exc_info=True)


class NotificationsService:
    def __init__(self, db):
        self.db = db
        self.collection = db[COLLECTION]

    @staticmethod
    def _out(doc) -> NotificationOut:
        return NotificationOut(
            id=doc["_id"],
            kind=doc["kind"],
            title=doc["title"],
            body=doc.get("body") or "",
            link=doc.get("link"),
            read_at=doc.get("read_at"),
            created_at=doc["created_at"],
        )

    async def list(self, user_id: UUID, limit: int = 30) -> NotificationList:
        docs = (
            await self.collection.find({"user_id": user_id})
            .sort("created_at", -1)
            .limit(limit)
            .to_list(length=limit)
        )
        unread = await self.collection.count_documents(
            {"user_id": user_id, "read_at": None}
        )
        return NotificationList(
            notifications=[self._out(doc) for doc in docs], unread_count=unread
        )

    async def mark_read(self, user_id: UUID, notification_id: UUID) -> NotificationOut:
        doc = await self.collection.find_one(
            {"_id": notification_id, "user_id": user_id}
        )
        if doc is None:
            raise ProviderError("notification_not_found")
        if doc.get("read_at") is None:
            await self.collection.update_one(
                {"_id": notification_id}, {"$set": {"read_at": utcnow()}}
            )
            doc = await self.collection.find_one({"_id": notification_id})
        return self._out(doc)

    async def mark_all_read(self, user_id: UUID) -> NotificationList:
        await self.collection.update_many(
            {"user_id": user_id, "read_at": None}, {"$set": {"read_at": utcnow()}}
        )
        return await self.list(user_id)
