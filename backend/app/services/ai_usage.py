"""AI Usage & Cost Analytics service.

Built entirely on records MindFlow already stores — no new tracking
pipeline, no duplicate logging:

- `ai_requests` (written by ChatRepository.record_request for every AI
  call: chat, agents via chat path, code analyzer, template assistant)
  is the source for overview / timeseries / providers / models /
  history. It carries conversation_id but no agent/workflow id, so
  per-workflow token cost is reported as untracked, never estimated.
- `agent_executions` carries per-agent provider/model/tokens and an
  estimated_cost computed at execution time — the source for the
  per-agent breakdown.
- Prices come from the caller's synced `ai_models`
  (input/output_price_per_token) overlaid with the caller's own
  `ai_pricing` overrides (per-1M prices, versioned, never overwritten
  in place — each update bumps the version and replaces the row, the
  usage record keeps the computed estimate only).

Costs are estimates from those prices and stay None when no priced
model covers the rows. All queries are owner-scoped.
"""

import uuid
from datetime import datetime, time, timedelta
from uuid import UUID

from app.models.base import utcnow
from app.schemas.ai_usage import (
    AgentUsageOut,
    BudgetStatusOut,
    ModelUsageOut,
    PricingRowOut,
    ProviderUsageOut,
    TimeseriesPointOut,
    UsageHistoryItemOut,
    UsageHistoryOut,
    UsageOverviewOut,
    UsageTotalsOut,
    WorkflowUsageOut,
)
from app.services.analytics import AnalyticsService
from app.services.notifications import notify

PRICING_COLLECTION = "ai_pricing"
BUDGETS_COLLECTION = "ai_budgets"
_PER_1M = 1_000_000


def resolve_range(
    preset: str, start: datetime | None, end: datetime | None
) -> tuple[datetime, datetime]:
    """Resolve a range preset (or a custom start/end) to datetimes."""
    now = utcnow()
    if preset == "custom" and start is not None:
        return start, end or now
    today = now.date()
    if preset == "today":
        begin = datetime.combine(today, time.min, tzinfo=now.tzinfo)
        return begin, now
    if preset == "7d":
        return now - timedelta(days=7), now
    if preset == "month":
        begin = datetime(today.year, today.month, 1, tzinfo=now.tzinfo)
        return begin, now
    if preset == "last_month":
        first_this = datetime(today.year, today.month, 1, tzinfo=now.tzinfo)
        prev_month_end = first_this - timedelta(days=1)
        begin = datetime(
            prev_month_end.year, prev_month_end.month, 1, tzinfo=now.tzinfo
        )
        return begin, first_this
    return now - timedelta(days=30), now


class AIUsageService:
    def __init__(self, db):
        self.db = db
        self.analytics = AnalyticsService(db)

    # -- shared helpers ----------------------------------------------------

    async def _price_map(self, user_id: UUID) -> dict[tuple[str, str], tuple]:
        prices = await self.analytics._price_map(user_id)
        overrides = await self.db[PRICING_COLLECTION].find(
            {"user_id": user_id}
        ).to_list(length=1000)
        for row in overrides:
            prices[(row["provider"], row["model"])] = (
                row.get("input_price_per_token"),
                row.get("output_price_per_token"),
            )
        return prices

    async def _rows(
        self, user_id: UUID, start: datetime, end: datetime
    ) -> list[dict]:
        return await self.db.ai_requests.find(
            {"user_id": user_id, "created_at": {"$gte": start, "$lte": end}},
            {
                "provider": 1,
                "model": 1,
                "status": 1,
                "conversation_id": 1,
                "input_tokens": 1,
                "output_tokens": 1,
                "latency_ms": 1,
                "created_at": 1,
            },
        ).to_list(length=100000)

    @staticmethod
    def _row_cost(row: dict, prices: dict) -> float | None:
        price = prices.get((row.get("provider"), row.get("model")))
        if not price or price[0] is None or price[1] is None:
            return None
        return (row.get("input_tokens") or 0) * price[0] + (
            row.get("output_tokens") or 0
        ) * price[1]

    def _totals(self, rows: list[dict], prices: dict) -> UsageTotalsOut:
        window = self.analytics._window(rows, prices)
        return UsageTotalsOut(
            requests=window.requests,
            successful=window.successful,
            failed=window.failed,
            input_tokens=window.input_tokens,
            output_tokens=window.output_tokens,
            total_tokens=window.input_tokens + window.output_tokens,
            avg_latency_ms=window.avg_latency_ms,
            cost_estimate=window.cost_estimate,
            unpriced_requests=window.unpriced_requests,
            avg_cost_per_request=(
                window.cost_estimate / window.requests
                if window.cost_estimate is not None and window.requests
                else None
            ),
        )

    # -- analytics ---------------------------------------------------------

    async def overview(
        self, user_id: UUID, preset: str, start, end
    ) -> UsageOverviewOut:
        begin, finish = resolve_range(preset, start, end)
        rows = await self._rows(user_id, begin, finish)
        prices = await self._price_map(user_id)
        return UsageOverviewOut(
            range_preset=preset,
            start=begin,
            end=finish,
            totals=self._totals(rows, prices),
        )

    async def timeseries(
        self, user_id: UUID, preset: str, start, end
    ) -> list[TimeseriesPointOut]:
        begin, finish = resolve_range(preset, start, end)
        rows = await self._rows(user_id, begin, finish)
        prices = await self._price_map(user_id)
        by_day: dict[str, list[dict]] = {}
        for row in rows:
            by_day.setdefault(row["created_at"].date().isoformat(), []).append(row)
        points = []
        day = begin.date()
        last = finish.date()
        while day <= last:
            key = day.isoformat()
            day_rows = by_day.get(key, [])
            totals = self._totals(day_rows, prices)
            points.append(
                TimeseriesPointOut(
                    date=key,
                    requests=totals.requests,
                    input_tokens=totals.input_tokens,
                    output_tokens=totals.output_tokens,
                    total_tokens=totals.total_tokens,
                    cost_estimate=totals.cost_estimate,
                )
            )
            day += timedelta(days=1)
        return points

    async def providers(
        self, user_id: UUID, preset: str, start, end
    ) -> list[ProviderUsageOut]:
        begin, finish = resolve_range(preset, start, end)
        rows = await self._rows(user_id, begin, finish)
        prices = await self._price_map(user_id)
        grouped: dict[str, list[dict]] = {}
        for row in rows:
            grouped.setdefault(row.get("provider") or "", []).append(row)
        out = []
        for provider, group in grouped.items():
            totals = self._totals(group, prices)
            out.append(
                ProviderUsageOut(
                    provider=provider,
                    requests=totals.requests,
                    input_tokens=totals.input_tokens,
                    output_tokens=totals.output_tokens,
                    total_tokens=totals.total_tokens,
                    avg_latency_ms=totals.avg_latency_ms,
                    cost_estimate=totals.cost_estimate,
                    unpriced_requests=totals.unpriced_requests,
                )
            )
        out.sort(key=lambda item: -item.requests)
        return out

    async def models(
        self, user_id: UUID, preset: str, start, end, sort: str
    ) -> list[ModelUsageOut]:
        begin, finish = resolve_range(preset, start, end)
        rows = await self._rows(user_id, begin, finish)
        prices = await self._price_map(user_id)
        grouped: dict[tuple[str, str], list[dict]] = {}
        for row in rows:
            grouped.setdefault(
                (row.get("provider") or "", row.get("model") or ""), []
            ).append(row)
        out = []
        for (provider, model), group in grouped.items():
            totals = self._totals(group, prices)
            out.append(
                ModelUsageOut(
                    provider=provider,
                    model=model,
                    requests=totals.requests,
                    input_tokens=totals.input_tokens,
                    output_tokens=totals.output_tokens,
                    total_tokens=totals.total_tokens,
                    avg_latency_ms=totals.avg_latency_ms,
                    success_rate=(
                        totals.successful / totals.requests if totals.requests else None
                    ),
                    cost_estimate=totals.cost_estimate,
                    unpriced_requests=totals.unpriced_requests,
                )
            )
        if sort == "cost":
            out.sort(key=lambda item: -(item.cost_estimate or 0))
        elif sort == "latency":
            out.sort(key=lambda item: -(item.avg_latency_ms or 0))
        elif sort == "tokens":
            out.sort(key=lambda item: -item.total_tokens)
        else:
            out.sort(key=lambda item: -item.requests)
        return out

    async def agents(
        self, user_id: UUID, preset: str, start, end
    ) -> list[AgentUsageOut]:
        begin, finish = resolve_range(preset, start, end)
        executions = await self.db.agent_executions.find(
            {"user_id": user_id, "created_at": {"$gte": begin, "$lte": finish}}
        ).to_list(length=100000)
        names: dict[str, str] = {}
        agent_rows = await self.db.agents.find({"user_id": user_id}).to_list(
            length=1000
        )
        for agent in agent_rows:
            names[str(agent["_id"])] = agent.get("name", "")
        grouped: dict[tuple[str, str, str], list[dict]] = {}
        for row in executions:
            grouped.setdefault(
                (
                    str(row.get("agent_id", "")),
                    row.get("provider") or "",
                    row.get("model") or "",
                ),
                [],
            ).append(row)
        out = []
        for (agent_id, provider, model), group in grouped.items():
            costs = [
                row["estimated_cost"]
                for row in group
                if row.get("estimated_cost") is not None
            ]
            finished = sum(
                1 for row in group if row.get("status") in ("completed", "failed")
            )
            out.append(
                AgentUsageOut(
                    agent_id=agent_id,
                    agent_name=names.get(agent_id, ""),
                    provider=provider,
                    model=model,
                    executions=len(group),
                    input_tokens=sum(row.get("input_tokens") or 0 for row in group),
                    output_tokens=sum(row.get("output_tokens") or 0 for row in group),
                    total_tokens=sum(
                        (row.get("input_tokens") or 0)
                        + (row.get("output_tokens") or 0)
                        for row in group
                    ),
                    estimated_cost=sum(costs) if costs else None,
                    success_rate=(
                        sum(1 for row in group if row.get("status") == "completed")
                        / finished
                        if finished
                        else None
                    ),
                )
            )
        out.sort(key=lambda item: -item.total_tokens)
        return out

    async def workflows(self, user_id: UUID) -> list[WorkflowUsageOut]:
        out = []
        for source, collection in (
            ("agent_workflows", "agent_workflows"),
            ("n8n_factory", "n8n_factory_runs"),
        ):
            rows = await self.db[collection].find(
                {"user_id": user_id}, {"status": 1}
            ).to_list(length=100000)
            by_status: dict[str, int] = {}
            for row in rows:
                status = row.get("status") or "unknown"
                by_status[status] = by_status.get(status, 0) + 1
            out.append(
                WorkflowUsageOut(
                    source=source,
                    executions=len(rows),
                    by_status=by_status,
                    usage_tracked=False,
                )
            )
        return out

    # -- history -----------------------------------------------------------

    async def _history_rows(
        self,
        user_id: UUID,
        preset: str,
        start,
        end,
        provider: str | None,
        model: str | None,
        status: str | None,
    ) -> tuple[list[dict], dict]:
        begin, finish = resolve_range(preset, start, end)
        rows = await self._rows(user_id, begin, finish)
        if provider:
            rows = [row for row in rows if row.get("provider") == provider]
        if model:
            rows = [row for row in rows if row.get("model") == model]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        rows.sort(key=lambda row: row["created_at"], reverse=True)
        prices = await self._price_map(user_id)
        return rows, prices

    def _history_item(self, row: dict, prices: dict) -> UsageHistoryItemOut:
        input_tokens = row.get("input_tokens")
        output_tokens = row.get("output_tokens")
        return UsageHistoryItemOut(
            id=str(row["_id"]),
            created_at=row["created_at"],
            provider=row.get("provider") or "",
            model=row.get("model") or "",
            conversation_id=(
                str(row["conversation_id"]) if row.get("conversation_id") else None
            ),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=(
                (input_tokens or 0) + (output_tokens or 0)
                if input_tokens is not None or output_tokens is not None
                else None
            ),
            cost_estimate=self._row_cost(row, prices),
            latency_ms=row.get("latency_ms"),
            status=row.get("status") or "",
        )

    async def history(
        self,
        user_id: UUID,
        preset: str,
        start,
        end,
        provider: str | None,
        model: str | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> UsageHistoryOut:
        rows, prices = await self._history_rows(
            user_id, preset, start, end, provider, model, status
        )
        page = rows[offset : offset + limit]
        return UsageHistoryOut(
            items=[self._history_item(row, prices) for row in page],
            total=len(rows),
            limit=limit,
            offset=offset,
        )

    async def export_csv(
        self,
        user_id: UUID,
        preset: str,
        start,
        end,
        provider: str | None,
        model: str | None,
        status: str | None,
    ) -> str:
        rows, prices = await self._history_rows(
            user_id, preset, start, end, provider, model, status
        )
        lines = [
            "time,provider,model,conversation_id,input_tokens,output_tokens,"
            "total_tokens,cost_usd,latency_ms,status"
        ]
        for row in rows[:5000]:
            item = self._history_item(row, prices)
            lines.append(
                ",".join(
                    [
                        item.created_at.isoformat(),
                        item.provider,
                        item.model,
                        item.conversation_id or "",
                        "" if item.input_tokens is None else str(item.input_tokens),
                        "" if item.output_tokens is None else str(item.output_tokens),
                        "" if item.total_tokens is None else str(item.total_tokens),
                        "" if item.cost_estimate is None else f"{item.cost_estimate:.6f}",
                        "" if item.latency_ms is None else str(item.latency_ms),
                        item.status,
                    ]
                )
            )
        return "\n".join(lines) + "\n"

    # -- pricing -----------------------------------------------------------

    async def pricing(self, user_id: UUID) -> list[PricingRowOut]:
        prices = await self.analytics._price_map(user_id)
        overrides = await self.db[PRICING_COLLECTION].find(
            {"user_id": user_id}
        ).to_list(length=1000)
        override_map = {(row["provider"], row["model"]): row for row in overrides}
        out = []
        for (provider, model), (in_price, out_price) in sorted(prices.items()):
            override = override_map.get((provider, model))
            if override is not None:
                out.append(
                    PricingRowOut(
                        provider=provider,
                        model=model,
                        input_price_per_1m=override["input_price_per_1m"],
                        output_price_per_1m=override["output_price_per_1m"],
                        source="override",
                        version=override.get("version"),
                        updated_at=override.get("updated_at"),
                    )
                )
            else:
                out.append(
                    PricingRowOut(
                        provider=provider,
                        model=model,
                        input_price_per_1m=(
                            in_price * _PER_1M if in_price is not None else None
                        ),
                        output_price_per_1m=(
                            out_price * _PER_1M if out_price is not None else None
                        ),
                        source="synced",
                        version=None,
                        updated_at=None,
                    )
                )
        for (provider, model), row in override_map.items():
            if (provider, model) not in prices:
                out.append(
                    PricingRowOut(
                        provider=provider,
                        model=model,
                        input_price_per_1m=row["input_price_per_1m"],
                        output_price_per_1m=row["output_price_per_1m"],
                        source="override",
                        version=row.get("version"),
                        updated_at=row.get("updated_at"),
                    )
                )
        return out

    async def update_pricing(self, user_id: UUID, payload) -> PricingRowOut:
        existing = await self.db[PRICING_COLLECTION].find_one(
            {
                "user_id": user_id,
                "provider": payload.provider,
                "model": payload.model,
            }
        )
        version = (existing.get("version", 0) if existing else 0) + 1
        doc = {
            "_id": existing["_id"] if existing else uuid.uuid4().hex,
            "user_id": user_id,
            "provider": payload.provider,
            "model": payload.model,
            "input_price_per_1m": payload.input_price_per_1m,
            "output_price_per_1m": payload.output_price_per_1m,
            "input_price_per_token": payload.input_price_per_1m / _PER_1M,
            "output_price_per_token": payload.output_price_per_1m / _PER_1M,
            "version": version,
            "updated_at": utcnow(),
        }
        await self.db[PRICING_COLLECTION].replace_one(
            {"_id": doc["_id"]}, doc, upsert=True
        )
        return PricingRowOut(
            provider=doc["provider"],
            model=doc["model"],
            input_price_per_1m=doc["input_price_per_1m"],
            output_price_per_1m=doc["output_price_per_1m"],
            source="override",
            version=version,
            updated_at=doc["updated_at"],
        )

    # -- budgets -----------------------------------------------------------

    async def _month_spend(
        self, user_id: UUID, budget: dict, prices: dict
    ) -> float | None:
        now = utcnow()
        begin = datetime(now.year, now.month, 1, tzinfo=now.tzinfo)
        if budget["scope_type"] == "agent":
            executions = await self.db.agent_executions.find(
                {
                    "user_id": user_id,
                    "created_at": {"$gte": begin},
                }
            ).to_list(length=100000)
            costs = [
                row["estimated_cost"]
                for row in executions
                if str(row.get("agent_id", "")) == budget.get("scope_id", "")
                and row.get("estimated_cost") is not None
            ]
            return sum(costs) if costs else None
        rows = await self._rows(user_id, begin, now)
        if budget["scope_type"] == "provider":
            rows = [
                row for row in rows if row.get("provider") == budget.get("scope_id")
            ]
        totals = self._totals(rows, prices)
        return totals.cost_estimate

    async def budgets(self, user_id: UUID) -> list[BudgetStatusOut]:
        prices = await self._price_map(user_id)
        docs = await self.db[BUDGETS_COLLECTION].find({"user_id": user_id}).to_list(
            length=100
        )
        now = utcnow()
        month_key = f"{now.year}-{now.month:02d}"
        out = []
        for doc in docs:
            spent = await self._month_spend(user_id, doc, prices)
            limit = doc["monthly_limit_usd"]
            percent = (spent / limit * 100) if spent is not None else None
            level = (
                100
                if percent is not None and percent >= 100
                else 80
                if percent is not None and percent >= 80
                else 50
                if percent is not None and percent >= 50
                else 0
            )
            if level > 0 and (
                doc.get("last_alert_month") != month_key
                or level > doc.get("last_alert_level", 0)
            ):
                await notify(
                    self.db,
                    user_id,
                    kind="budget_alert",
                    title=f"Ngân sách AI đạt {level}%",
                    body=(
                        f"Ngân sách {doc['scope_type']}"
                        f"{(' ' + doc['scope_id']) if doc.get('scope_id') else ''} "
                        f"đã dùng {percent:.0f}% ({spent:.2f}$ / {limit:.2f}$) "
                        f"trong tháng {month_key}."
                    ),
                    link="/analytics",
                )
                await self.db[BUDGETS_COLLECTION].update_one(
                    {"_id": doc["_id"]},
                    {
                        "$set": {
                            "last_alert_month": month_key,
                            "last_alert_level": level,
                        }
                    },
                )
            out.append(
                BudgetStatusOut(
                    id=str(doc["_id"]),
                    scope_type=doc["scope_type"],
                    scope_id=doc.get("scope_id", ""),
                    monthly_limit_usd=limit,
                    spent_usd=spent,
                    remaining_usd=(
                        max(limit - spent, 0.0) if spent is not None else None
                    ),
                    percent_used=percent,
                    alert_level=level,
                )
            )
        return out

    async def upsert_budget(self, user_id: UUID, payload) -> BudgetStatusOut:
        existing = await self.db[BUDGETS_COLLECTION].find_one(
            {
                "user_id": user_id,
                "scope_type": payload.scope_type,
                "scope_id": payload.scope_id,
            }
        )
        doc = {
            "_id": existing["_id"] if existing else uuid.uuid4().hex,
            "user_id": user_id,
            "scope_type": payload.scope_type,
            "scope_id": payload.scope_id,
            "monthly_limit_usd": payload.monthly_limit_usd,
            "last_alert_month": existing.get("last_alert_month") if existing else None,
            "last_alert_level": existing.get("last_alert_level", 0) if existing else 0,
            "updated_at": utcnow(),
        }
        await self.db[BUDGETS_COLLECTION].replace_one(
            {"_id": doc["_id"]}, doc, upsert=True
        )
        statuses = await self.budgets(user_id)
        for status in statuses:
            if (
                status.scope_type == payload.scope_type
                and status.scope_id == payload.scope_id
            ):
                return status
        raise RuntimeError("budget upsert did not persist")
