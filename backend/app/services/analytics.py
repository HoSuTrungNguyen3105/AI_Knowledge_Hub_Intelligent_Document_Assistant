"""Executive analytics for the caller's own account (NEXORA Module 01).

Everything is computed from records the system already stores —
`ai_requests` (provider-reported usage/latency), `agent_workflows`,
`agent_tasks`, `n8n_factory_runs`, `agents`, `agent_teams`,
`activity_logs`. Nothing is sampled or fabricated: costs are estimates
derived from the caller's own synced model prices and are reported as
None when no priced model covers a request.

Aggregation runs in Python over bounded finds (30 days of AI requests;
status-only projections elsewhere), which keeps the numbers identical
in production and in the offline test suite.
"""

from datetime import UTC, timedelta
from decimal import Decimal
from uuid import UUID

from app.models.base import utcnow
from app.schemas.analytics import (
    AnalyticsOverview,
    DayUsage,
    ModelUsage,
    StatusCounts,
    TaskStats,
    UsageWindow,
    WorkflowStats,
)
from app.schemas.dashboard import ActivityResponse


def _aware(value):
    """Treat a naive stored datetime as UTC.

    Rows written by older code paths or seed scripts may carry naive
    datetimes; comparing them with aware cutoffs raises TypeError and
    used to take the whole overview down as a bare 500.
    """
    if value is not None and getattr(value, "tzinfo", None) is None:
        return value.replace(tzinfo=UTC)
    return value


def _as_int(value) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    return 0


def _as_float(value):
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    return None


class AnalyticsService:
    def __init__(self, db):
        self.db = db

    async def _price_map(self, user_id: UUID) -> dict[tuple[str, str], tuple]:
        prices: dict[tuple[str, str], tuple] = {}
        credentials = await self.db.user_provider_credentials.find(
            {"user_id": user_id}
        ).to_list(length=100)
        for credential in credentials:
            provider = credential.get("provider")
            if not isinstance(provider, str) or not provider:
                continue
            models = await self.db.ai_models.find(
                {"credential_id": credential["_id"]}
            ).to_list(length=1000)
            for model in models:
                # Some providers' synced rows carry a non-string record
                # id instead of a model name (the same malformed rows
                # that crashed the template assistant's auto-pick) —
                # skip anything that is not a callable model name.
                model_id = model.get("model_id") or model.get("id")
                if not isinstance(model_id, str) or not model_id:
                    continue
                # Prices are coerced to floats here: a price stored as a
                # string or Decimal128 would otherwise poison the cost
                # multiplication in _window (int * str raises TypeError)
                # and take the whole overview down. A non-numeric price
                # simply leaves the model unpriced.
                prices[(provider, model_id)] = (
                    _as_float(model.get("input_price_per_token")),
                    _as_float(model.get("output_price_per_token")),
                )
        return prices

    @staticmethod
    def _window(rows: list[dict], prices: dict) -> UsageWindow:
        latencies = [
            value
            for r in rows
            if (value := _as_float(r.get("latency_ms"))) is not None
        ]
        cost = 0.0
        priced = False
        unpriced = 0
        for row in rows:
            price_key = (
                row.get("provider") if isinstance(row.get("provider"), str) else "",
                row.get("model") if isinstance(row.get("model"), str) else "",
            )
            price = prices.get(price_key)
            if price and price[0] is not None and price[1] is not None:
                cost += _as_int(row.get("input_tokens")) * price[0]
                cost += _as_int(row.get("output_tokens")) * price[1]
                priced = True
            else:
                unpriced += 1
        return UsageWindow(
            requests=len(rows),
            successful=sum(1 for r in rows if r.get("status") == "success"),
            failed=sum(1 for r in rows if r.get("status") == "error"),
            input_tokens=sum(_as_int(r.get("input_tokens")) for r in rows),
            output_tokens=sum(_as_int(r.get("output_tokens")) for r in rows),
            avg_latency_ms=(sum(latencies) / len(latencies) if latencies else None),
            cost_estimate=cost if priced else None,
            unpriced_requests=unpriced,
        )

    @staticmethod
    def _counts(rows: list[dict]) -> tuple[int, dict[str, int]]:
        by_status: dict[str, int] = {}
        for row in rows:
            status = str(row.get("status") or "unknown")
            by_status[status] = by_status.get(status, 0) + 1
        return len(rows), by_status

    @staticmethod
    def _activity(row: dict) -> ActivityResponse | None:
        """Build one activity entry, skipping rows whose stored shape
        cannot be represented (non-UUID id, missing timestamp) instead
        of failing the whole overview."""
        created_at = _aware(row.get("created_at"))
        if created_at is None:
            return None
        try:
            activity_id = row["_id"]
            if not isinstance(activity_id, UUID):
                activity_id = UUID(str(activity_id))
        except (KeyError, ValueError, TypeError):
            return None
        return ActivityResponse(
            id=activity_id,
            action=str(row.get("action") or ""),
            description=str(row.get("description") or ""),
            created_at=created_at,
        )

    async def overview(self, user_id: UUID) -> AnalyticsOverview:
        now = utcnow()
        since30 = now - timedelta(days=30)
        since7 = now - timedelta(days=7)

        request_rows = await self.db.ai_requests.find(
            {"user_id": user_id, "created_at": {"$gte": since30}},
            {
                "provider": 1,
                "model": 1,
                "status": 1,
                "input_tokens": 1,
                "output_tokens": 1,
                "latency_ms": 1,
                "created_at": 1,
            },
        ).to_list(length=100000)
        for row in request_rows:
            row["created_at"] = _aware(row.get("created_at"))
        prices = await self._price_map(user_id)
        rows7 = [
            r
            for r in request_rows
            if r.get("created_at") is not None and r["created_at"] >= since7
        ]

        by_model: dict[tuple[str, str], list[dict]] = {}
        for row in request_rows:
            key = (
                row.get("provider") if isinstance(row.get("provider"), str) else "",
                row.get("model") if isinstance(row.get("model"), str) else "",
            )
            by_model.setdefault(key, []).append(row)
        models = []
        for (provider, model), rows in by_model.items():
            window = self._window(rows, prices)
            models.append(
                ModelUsage(
                    provider=provider,
                    model=model,
                    requests=window.requests,
                    input_tokens=window.input_tokens,
                    output_tokens=window.output_tokens,
                    cost_estimate=window.cost_estimate,
                )
            )
        models.sort(key=lambda item: -item.requests)

        daily = []
        for offset in range(13, -1, -1):
            day = (now - timedelta(days=offset)).date()
            day_rows = [
                r
                for r in request_rows
                if r.get("created_at") is not None and r["created_at"].date() == day
            ]
            daily.append(
                DayUsage(
                    date=day.isoformat(),
                    requests=len(day_rows),
                    input_tokens=sum(_as_int(r.get("input_tokens")) for r in day_rows),
                    output_tokens=sum(_as_int(r.get("output_tokens")) for r in day_rows),
                )
            )

        workflow_rows = await self.db.agent_workflows.find(
            {"user_id": user_id}, {"status": 1}
        ).to_list(length=100000)
        wf_total, wf_by_status = self._counts(workflow_rows)
        finished = sum(
            wf_by_status.get(status, 0) for status in ("completed", "failed", "cancelled")
        )
        workflows = WorkflowStats(
            total=wf_total,
            by_status=wf_by_status,
            success_rate=(wf_by_status.get("completed", 0) / finished) if finished else None,
        )

        workflow_ids = [row["_id"] for row in workflow_rows]
        task_rows = (
            await self.db.agent_tasks.find(
                {"workflow_id": {"$in": workflow_ids}}, {"status": 1}
            ).to_list(length=100000)
            if workflow_ids
            else []
        )
        task_total, task_by_status = self._counts(task_rows)
        task_finished = task_by_status.get("completed", 0) + task_by_status.get("failed", 0)
        tasks = TaskStats(
            total=task_total,
            by_status=task_by_status,
            completion_rate=(
                task_by_status.get("completed", 0) / task_finished if task_finished else None
            ),
        )

        factory_rows = await self.db.n8n_factory_runs.find(
            {"user_id": user_id}, {"status": 1}
        ).to_list(length=100000)
        factory_total, factory_by_status = self._counts(factory_rows)

        activity_rows = (
            await self.db.activity_logs.find({"user_id": user_id})
            .sort("created_at", -1)
            .limit(8)
            .to_list(length=8)
        )

        return AnalyticsOverview(
            agents_total=await self.db.agents.count_documents({"user_id": user_id}),
            agents_demo=await self.db.agents.count_documents(
                {"user_id": user_id, "is_demo": True}
            ),
            teams_total=await self.db.agent_teams.count_documents({"user_id": user_id}),
            teams_demo=await self.db.agent_teams.count_documents(
                {"user_id": user_id, "is_demo": True}
            ),
            workflows=workflows,
            tasks=tasks,
            factory_runs=StatusCounts(total=factory_total, by_status=factory_by_status),
            usage_7d=self._window(rows7, prices),
            usage_30d=self._window(request_rows, prices),
            models_30d=models,
            daily_14d=daily,
            recent_activity=[
                activity
                for row in activity_rows
                if (activity := self._activity(row)) is not None
            ],
        )
