from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.repositories.dashboard import DashboardRepository
from app.schemas.dashboard import ActivityResponse, DashboardResponse


async def get_dashboard(db: AsyncIOMotorDatabase, user_id: UUID) -> DashboardResponse:
    repository = DashboardRepository(db)
    totals = await repository.totals(user_id)
    activities = await repository.recent_activity(user_id)
    return DashboardResponse(
        **totals,
        recent_activity=[ActivityResponse.model_validate(activity) for activity in activities],
    )