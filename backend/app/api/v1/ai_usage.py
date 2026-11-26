"""AI Usage & Cost Analytics endpoints.

Prefix: ``/ai/ai-usage``. All endpoints are owner-scoped: a user only
ever sees usage recorded under their own account. Data comes from
`ai_requests` / `agent_executions` and the caller's own model prices —
see app.services.ai_usage for the honesty rules (no fabricated costs).
"""

from datetime import datetime

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from app.api.dependencies import CurrentUser, Database
from app.schemas.ai_usage import (
    AgentUsageOut,
    BudgetIn,
    BudgetStatusOut,
    ModelUsageOut,
    PricingRowOut,
    PricingUpdateIn,
    ProviderUsageOut,
    TimeseriesPointOut,
    UsageHistoryOut,
    UsageOverviewOut,
    WorkflowUsageOut,
)
from app.services.ai_usage import AIUsageService

router = APIRouter(prefix="/ai/ai-usage", tags=["ai-usage"])

RangePreset = Query(default="30d", pattern="^(today|7d|30d|month|last_month|custom)$")


@router.get("/overview", response_model=UsageOverviewOut)
async def usage_overview(
    user: CurrentUser,
    db: Database,
    preset: str = RangePreset,
    start: datetime | None = None,
    end: datetime | None = None,
) -> UsageOverviewOut:
    return await AIUsageService(db).overview(user.id, preset, start, end)


@router.get("/timeseries", response_model=list[TimeseriesPointOut])
async def usage_timeseries(
    user: CurrentUser,
    db: Database,
    preset: str = RangePreset,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[TimeseriesPointOut]:
    return await AIUsageService(db).timeseries(user.id, preset, start, end)


@router.get("/providers", response_model=list[ProviderUsageOut])
async def usage_providers(
    user: CurrentUser,
    db: Database,
    preset: str = RangePreset,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[ProviderUsageOut]:
    return await AIUsageService(db).providers(user.id, preset, start, end)


@router.get("/models", response_model=list[ModelUsageOut])
async def usage_models(
    user: CurrentUser,
    db: Database,
    preset: str = RangePreset,
    start: datetime | None = None,
    end: datetime | None = None,
    sort: str = Query(default="requests", pattern="^(requests|tokens|cost|latency)$"),
) -> list[ModelUsageOut]:
    return await AIUsageService(db).models(user.id, preset, start, end, sort)


@router.get("/agents", response_model=list[AgentUsageOut])
async def usage_agents(
    user: CurrentUser,
    db: Database,
    preset: str = RangePreset,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[AgentUsageOut]:
    return await AIUsageService(db).agents(user.id, preset, start, end)


@router.get("/workflows", response_model=list[WorkflowUsageOut])
async def usage_workflows(
    user: CurrentUser, db: Database
) -> list[WorkflowUsageOut]:
    return await AIUsageService(db).workflows(user.id)


@router.get("/history", response_model=UsageHistoryOut)
async def usage_history(
    user: CurrentUser,
    db: Database,
    preset: str = RangePreset,
    start: datetime | None = None,
    end: datetime | None = None,
    provider: str | None = None,
    model: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> UsageHistoryOut:
    return await AIUsageService(db).history(
        user.id, preset, start, end, provider, model, status, limit, offset
    )


@router.get("/export")
async def usage_export(
    user: CurrentUser,
    db: Database,
    preset: str = RangePreset,
    start: datetime | None = None,
    end: datetime | None = None,
    provider: str | None = None,
    model: str | None = None,
    status: str | None = None,
) -> PlainTextResponse:
    csv_text = await AIUsageService(db).export_csv(
        user.id, preset, start, end, provider, model, status
    )
    return PlainTextResponse(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=ai-usage.csv"},
    )


@router.get("/pricing", response_model=list[PricingRowOut])
async def usage_pricing(
    user: CurrentUser, db: Database
) -> list[PricingRowOut]:
    return await AIUsageService(db).pricing(user.id)


@router.put("/pricing", response_model=PricingRowOut)
async def usage_pricing_update(
    payload: PricingUpdateIn, user: CurrentUser, db: Database
) -> PricingRowOut:
    return await AIUsageService(db).update_pricing(user.id, payload)


@router.get("/budgets", response_model=list[BudgetStatusOut])
async def usage_budgets(
    user: CurrentUser, db: Database
) -> list[BudgetStatusOut]:
    return await AIUsageService(db).budgets(user.id)


@router.put("/budgets", response_model=BudgetStatusOut)
async def usage_budgets_upsert(
    payload: BudgetIn, user: CurrentUser, db: Database
) -> BudgetStatusOut:
    return await AIUsageService(db).upsert_budget(user.id, payload)
