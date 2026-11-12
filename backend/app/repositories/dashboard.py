from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models import ActivityLog, AIRequest, Conversation, Document, KnowledgeBase


class DashboardRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    async def totals(self, user_id: UUID) -> dict[str, int]:
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$group": {"_id": None, "count": {"$sum": 1}}},
        ]
        resources = {
            "total_documents": self.db.documents,
            "total_knowledge_bases": self.db.knowledge_bases,
            "total_conversations": self.db.conversations,
            "ai_requests_usage": self.db.ai_requests,
        }
        result = {}
        for label, collection in resources.items():
            cursor = collection.aggregate(pipeline)
            docs = await cursor.to_list(length=1)
            result[label] = docs[0]["count"] if docs else 0
        return result

    async def recent_activity(self, user_id: UUID) -> list[ActivityLog]:
        cursor = (
            self.db.activity_logs.find({"user_id": user_id})
            .sort("created_at", -1)
            .limit(10)
        )
        return [ActivityLog(**doc) async for doc in cursor]