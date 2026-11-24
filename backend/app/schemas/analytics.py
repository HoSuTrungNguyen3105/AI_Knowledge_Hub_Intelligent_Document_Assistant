from pydantic import BaseModel

from app.schemas.dashboard import ActivityResponse


class StatusCounts(BaseModel):
    total: int
    by_status: dict[str, int]


class WorkflowStats(StatusCounts):
    # completed / (completed + failed + cancelled); None when nothing finished.
    success_rate: float | None


class TaskStats(StatusCounts):
    # completed / (completed + failed); None when nothing finished.
    completion_rate: float | None


class UsageWindow(BaseModel):
    requests: int
    successful: int
    failed: int
    input_tokens: int
    output_tokens: int
    avg_latency_ms: float | None
    # Estimate from the caller's own synced model prices; None when no
    # priced model was used in the window. Never a fabricated number.
    cost_estimate: float | None
    unpriced_requests: int


class ModelUsage(BaseModel):
    provider: str
    model: str
    requests: int
    input_tokens: int
    output_tokens: int
    cost_estimate: float | None


class DayUsage(BaseModel):
    date: str  # ISO date (UTC)
    requests: int
    input_tokens: int
    output_tokens: int


class AnalyticsOverview(BaseModel):
    agents_total: int
    agents_demo: int
    teams_total: int
    teams_demo: int
    workflows: WorkflowStats
    tasks: TaskStats
    factory_runs: StatusCounts
    usage_7d: UsageWindow
    usage_30d: UsageWindow
    models_30d: list[ModelUsage]
    daily_14d: list[DayUsage]
    recent_activity: list[ActivityResponse]
