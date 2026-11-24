from fastapi import APIRouter

from app.api.dependencies import CurrentUser, Database
from app.schemas.analytics import AnalyticsOverview
from app.services.analytics import AnalyticsService

router = APIRouter(tags=["Analytics"])


@router.get("/ai/analytics/overview", response_model=AnalyticsOverview)
async def analytics_overview(user: CurrentUser, db: Database) -> AnalyticsOverview:
    """Executive overview computed from the caller's real records:
    workflow/task outcomes, provider-reported token usage and latency,
    estimated cost from the caller's own synced model prices, model
    distribution, a 14-day usage series, and recent activity. Demo
    records (is_demo) are counted separately, never blended in."""
    return await AnalyticsService(db).overview(user.id)
