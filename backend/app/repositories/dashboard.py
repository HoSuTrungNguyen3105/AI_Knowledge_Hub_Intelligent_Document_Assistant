from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ActivityLog, AIRequest, Conversation, Document, KnowledgeBase


class DashboardRepository:
    def __init__(self, db: Session):
        self.db = db

    def totals(self, user_id: UUID) -> dict[str, int]:
        resources = {
            "total_documents": Document,
            "total_knowledge_bases": KnowledgeBase,
            "total_conversations": Conversation,
            "ai_requests_usage": AIRequest,
        }
        query = select(
            *[
                select(func.count())
                .select_from(model)
                .where(model.user_id == user_id)
                .scalar_subquery()
                .label(label)
                for label, model in resources.items()
            ]
        )
        return dict(self.db.execute(query).mappings().one())

    def recent_activity(self, user_id: UUID) -> list[ActivityLog]:
        return list(
            self.db.scalars(
                select(ActivityLog)
                .where(ActivityLog.user_id == user_id)
                .order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
                .limit(10)
            )
        )
