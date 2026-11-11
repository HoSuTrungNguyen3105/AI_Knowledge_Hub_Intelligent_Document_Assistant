from fastapi import APIRouter

from app.api.dependencies import CurrentUser, Database
from app.schemas.dashboard import DashboardResponse
from app.services.dashboard import get_dashboard

router = APIRouter(tags=["Dashboard"])


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(user: CurrentUser, db: Database) -> DashboardResponse:
    return get_dashboard(db, user.id)
