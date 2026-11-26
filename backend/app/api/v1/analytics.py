import logging

from fastapi import APIRouter

from app.api.dependencies import CurrentUser, Database
from app.schemas.analytics import AnalyticsOverview
from app.services.analytics import AnalyticsService

router = APIRouter(tags=["Analytics"])
logger = logging.getLogger(__name__)


@router.get("/ai/analytics/overview", response_model=AnalyticsOverview)
async def analytics_overview(user: CurrentUser, db: Database) -> AnalyticsOverview:
    """Executive overview computed from the caller's real records:
    workflow/task outcomes, provider-reported token usage and latency,
    estimated cost from the caller's own synced model prices, model
    distribution, a 14-day usage series, and recent activity. Demo
    records (is_demo) are counted separately, never blended in."""
    try:
        return await AnalyticsService(db).overview(user.id)
    except Exception:
        # The app-wide handler answers a bare 500 without a traceback;
        # log it here under a searchable tag so the real line is visible
        # in the backend logs if this ever fails again.
        logger.exception("analytics overview failed")
        raise
