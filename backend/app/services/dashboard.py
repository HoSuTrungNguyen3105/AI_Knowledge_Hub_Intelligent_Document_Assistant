from uuid import UUID

from sqlalchemy.orm import Session

from app.repositories.dashboard import DashboardRepository
from app.schemas.dashboard import ActivityResponse, DashboardResponse


def get_dashboard(db: Session, user_id: UUID) -> DashboardResponse:
    repository = DashboardRepository(db)
    return DashboardResponse(
        **repository.totals(user_id),
        recent_activity=[
            ActivityResponse.model_validate(activity)
            for activity in repository.recent_activity(user_id)
        ],
    )
