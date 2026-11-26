"""AI Usage & Cost Analytics schemas (update_features.md module).

Everything is computed from records the system already stores
(`ai_requests`, `agent_executions`, synced `ai_models` prices). Costs are
estimates from the caller's own prices and stay None when a request has
no priced model — never fabricated.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class UsageTotalsOut(BaseModel):
    requests: int
    successful: int
    failed: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    avg_latency_ms: float | None
    cost_estimate: float | None
    unpriced_requests: int
    avg_cost_per_request: float | None


class UsageOverviewOut(BaseModel):
    range_preset: str
    start: datetime
    end: datetime
    totals: UsageTotalsOut


class TimeseriesPointOut(BaseModel):
    date: str
    requests: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_estimate: float | None


class ProviderUsageOut(BaseModel):
    provider: str
    requests: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    avg_latency_ms: float | None
    cost_estimate: float | None
    unpriced_requests: int


class ModelUsageOut(BaseModel):
    provider: str
    model: str
    requests: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    avg_latency_ms: float | None
    success_rate: float | None
    cost_estimate: float | None
    unpriced_requests: int


class AgentUsageOut(BaseModel):
    agent_id: str
    agent_name: str
    provider: str
    model: str
    executions: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost: float | None
    success_rate: float | None


class WorkflowUsageOut(BaseModel):
    source: str  # agent_workflows | n8n_factory
    executions: int
    by_status: dict[str, int]
    # ai_requests carries no workflow id, so per-workflow token/cost is
    # not tracked yet — reported honestly instead of estimated.
    usage_tracked: bool = False


class UsageHistoryItemOut(BaseModel):
    id: str
    created_at: datetime
    provider: str
    model: str
    conversation_id: str | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    cost_estimate: float | None
    latency_ms: int | None
    status: str


class UsageHistoryOut(BaseModel):
    items: list[UsageHistoryItemOut]
    total: int
    limit: int
    offset: int


class PricingRowOut(BaseModel):
    provider: str
    model: str
    input_price_per_1m: float | None
    output_price_per_1m: float | None
    source: str  # synced | override
    version: int | None
    updated_at: datetime | None


class PricingUpdateIn(BaseModel):
    provider: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=200)
    input_price_per_1m: float = Field(ge=0)
    output_price_per_1m: float = Field(ge=0)


class BudgetIn(BaseModel):
    scope_type: str = Field(pattern="^(total|provider|agent)$")
    scope_id: str = Field(default="", max_length=200)
    monthly_limit_usd: float = Field(gt=0)


class BudgetStatusOut(BaseModel):
    id: str
    scope_type: str
    scope_id: str
    monthly_limit_usd: float
    spent_usd: float | None
    remaining_usd: float | None
    percent_used: float | None
    alert_level: int  # 0 | 50 | 80 | 100
