"""Team recommendation scoring + allocations (mindflow-workforce-feature
sections 4 + 6, wave 4).

Scoring is a deterministic weighted formula in the backend — never the
LLM (spec section 6.2). The explanation shown to the manager is built
from the score components, so every point can be audited:

  skills      0-50  matched required skills, weighted by level (x/5);
                    25 flat when the task names no required skill
  workload    0-20  humans: 20 * (1 - current_project_count / 5);
                    AI is not project-bound and always gets 20
  availability 0-15 available/connected 15, busy 5
  cost        0-15  cheapest in the task's eligible pool gets 15,
                    priciest 0, linear between; unknown cost is a
                    neutral 7.5
  type fit    -25   when the task suggests human/ai and the resource is
                    the other kind (a penalty, never an exclusion)

Hard constraints run BEFORE scoring and exclude outright (spec 6.3):
an AI whose denied_scopes intersect the task's scopes, a human marked
unavailable, a disconnected AI. Excluded resources are stored on the
allocation with their reason, and even a manual reassignment by the
manager cannot put an excluded-by-scope AI back on that task.
"""

from uuid import UUID, uuid4

from app.core.config import Settings
from app.models.base import utcnow
from app.schemas.allocations import (
    AllocationList,
    AllocationOut,
    DecideIn,
    ReassignIn,
    RecommendIn,
)
from app.services.ai.base_provider import ProviderError
from app.services.projects import ProjectService


def _exclusion_reason(task: dict, resource: dict) -> str | None:
    if resource["type"] == "ai":
        ai = resource.get("ai") or {}
        denied = {scope.lower() for scope in ai.get("denied_scopes", [])}
        hits = [scope for scope in task.get("scopes", []) if scope.lower() in denied]
        if hits:
            return f"AI bị cấm phạm vi: {', '.join(hits)} (ràng buộc cứng)"
        if resource["availability_status"] == "disconnected":
            return "AI chưa kết nối"
    elif resource["availability_status"] == "unavailable":
        return "Đang không khả dụng"
    return None


def _score(task: dict, resource: dict, pool_costs: list) -> tuple[float, str]:
    parts: list[str] = []
    required = task.get("skills_required", [])
    owned = {s["name"].lower(): s["level"] for s in resource.get("skills", [])}
    if required:
        hits, missing, total = [], [], 0.0
        for name in required:
            level = owned.get(name.lower())
            if level is None:
                missing.append(name)
            else:
                total += level / 5
                hits.append(f"{name} {level}/5")
        skill = 50 * total / len(required)
        if hits:
            parts.append(f"Khớp {len(hits)}/{len(required)} kỹ năng ({', '.join(hits)})")
        if missing:
            parts.append(f"Thiếu kỹ năng: {', '.join(missing)}")
    else:
        skill = 25.0
        parts.append("Task không yêu cầu kỹ năng cụ thể")

    if resource["type"] == "human":
        count = (resource.get("human") or {}).get("current_project_count") or 0
        workload = 20 * max(0.0, 1 - count / 5)
        if count == 0:
            parts.append("Đang rảnh, chưa tham gia dự án nào")
        else:
            parts.append(f"Đang tham gia {count} dự án")
    else:
        workload = 20.0
        parts.append("AI không bị giới hạn bởi số dự án đang chạy")

    if resource["availability_status"] in ("available", "connected"):
        availability = 15.0
        parts.append("Đang sẵn sàng nhận việc")
    else:
        availability = 5.0
        parts.append("Đang bận nhưng vẫn nhận được việc")

    cost = resource.get("cost_per_hour")
    if cost is None:
        cost_score = 7.5
        parts.append("Chưa khai chi phí")
    else:
        parts.append(f"Chi phí {cost}/giờ")
        known = [c for c in pool_costs if c is not None]
        if len(set(known)) <= 1:
            cost_score = 15.0
        else:
            cost_score = 15 * (max(known) - cost) / (max(known) - min(known))

    score = skill + workload + availability + cost_score
    suggested = task.get("suggested_type", "either")
    if suggested in ("human", "ai") and resource["type"] != suggested:
        score = max(0.0, score - 25)
        parts.append(f"Task gợi ý {'người' if suggested == 'human' else 'AI'} (-25 điểm)")
    return round(score, 2), "; ".join(parts)


class AllocationService:
    def __init__(self, db, settings: Settings):
        self.db = db
        self.projects = ProjectService(db, settings)

    # --- helpers ---------------------------------------------------------

    @staticmethod
    def _out(doc: dict) -> AllocationOut:
        return AllocationOut(
            id=doc["_id"],
            project_id=doc["project_id"],
            analysis_id=doc["analysis_id"],
            status=doc["status"],
            items=doc["items"],
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
            decided_at=doc.get("decided_at"),
        )

    async def _get_owned(
        self, user_id: UUID, project_id: UUID, allocation_id: UUID
    ) -> dict:
        await self.projects.get(user_id, project_id)  # 404 when not the owner's
        doc = await self.db.allocations.find_one(
            {"_id": allocation_id, "project_id": project_id, "user_id": user_id}
        )
        if doc is None:
            raise ProviderError("allocation_not_found")
        return doc

    @staticmethod
    def _require_proposed(doc: dict) -> None:
        if doc["status"] != "proposed":
            raise ProviderError("allocation_already_decided")

    # --- Recommendation ----------------------------------------------------

    async def recommend(
        self, user_id: UUID, project_id: UUID, payload: RecommendIn
    ) -> AllocationOut:
        await self.projects.get(user_id, project_id)
        query: dict = {"project_id": project_id, "user_id": user_id}
        if payload.analysis_id is not None:
            query["_id"] = payload.analysis_id
        analysis = await self.db.project_analyses.find_one(
            query, sort=[("created_at", -1)]
        )
        if analysis is None:
            raise ProviderError("analysis_not_found")

        resources = [
            doc async for doc in self.db.resources.find({"user_id": user_id})
        ]
        items = []
        for index, task in enumerate(analysis.get("tasks", [])):
            eligible, excluded = [], []
            for resource in resources:
                reason = _exclusion_reason(task, resource)
                if reason is not None:
                    excluded.append(
                        {
                            "resource_id": resource["_id"],
                            "name": resource["name"],
                            "reason": reason,
                        }
                    )
                else:
                    eligible.append(resource)
            pool_costs = [r.get("cost_per_hour") for r in eligible]
            candidates = []
            for resource in eligible:
                score, reason = _score(task, resource, pool_costs)
                candidates.append(
                    {
                        "resource_id": resource["_id"],
                        "name": resource["name"],
                        "type": resource["type"],
                        "score": score,
                        "reason": reason,
                        "cost_per_hour": resource.get("cost_per_hour"),
                    }
                )
            candidates.sort(key=lambda c: (-c["score"], c["name"].lower()))
            top = candidates[0] if candidates else None
            items.append(
                {
                    "task_index": index,
                    "task_title": task.get("title", ""),
                    "task_skills": task.get("skills_required", []),
                    "task_scopes": task.get("scopes", []),
                    "suggested_type": task.get("suggested_type", "either"),
                    "resource_id": top["resource_id"] if top else None,
                    "resource_name": top["name"] if top else None,
                    "resource_type": top["type"] if top else None,
                    "score": top["score"] if top else None,
                    "reason": top["reason"] if top else "Không có nguồn lực nào phù hợp.",
                    "candidates": candidates,
                    "excluded": excluded,
                }
            )

        now = utcnow()
        doc = {
            "_id": uuid4(),
            "user_id": user_id,
            "project_id": project_id,
            "analysis_id": analysis["_id"],
            "status": "proposed",
            "items": items,
            "created_at": now,
            "updated_at": now,
            "decided_at": None,
        }
        await self.db.allocations.insert_one(doc)
        return self._out(doc)

    async def list(self, user_id: UUID, project_id: UUID) -> AllocationList:
        await self.projects.get(user_id, project_id)
        cursor = self.db.allocations.find(
            {"project_id": project_id, "user_id": user_id}
        ).sort("created_at", -1)
        return AllocationList(allocations=[self._out(doc) async for doc in cursor])

    async def get(
        self, user_id: UUID, project_id: UUID, allocation_id: UUID
    ) -> AllocationOut:
        return self._out(await self._get_owned(user_id, project_id, allocation_id))

    # --- Manager adjustments + approval ------------------------------------

    async def reassign(
        self,
        user_id: UUID,
        project_id: UUID,
        allocation_id: UUID,
        payload: ReassignIn,
    ) -> AllocationOut:
        doc = await self._get_owned(user_id, project_id, allocation_id)
        self._require_proposed(doc)
        items = {item["task_index"]: item for item in doc["items"]}
        for change in payload.items:
            item = items.get(change.task_index)
            if item is None:
                raise ProviderError("allocation_not_found")
            if change.resource_id is None:
                item.update(
                    resource_id=None, resource_name=None, resource_type=None,
                    score=None, reason="Chưa phân công.",
                )
                continue
            resource = await self.db.resources.find_one(
                {"_id": change.resource_id, "user_id": user_id}
            )
            if resource is None:
                raise ProviderError("resource_not_found")
            task = {
                "skills_required": item["task_skills"],
                "scopes": item["task_scopes"],
                "suggested_type": item["suggested_type"],
            }
            exclusion = _exclusion_reason(task, resource)
            if exclusion is not None:
                raise ProviderError("allocation_hard_constraint")
            pool_costs = [c.get("cost_per_hour") for c in item["candidates"]]
            if resource.get("cost_per_hour") is not None:
                pool_costs.append(resource["cost_per_hour"])
            score, reason = _score(task, resource, pool_costs)
            item.update(
                resource_id=resource["_id"],
                resource_name=resource["name"],
                resource_type=resource["type"],
                score=score,
                reason=reason,
            )
        await self.db.allocations.update_one(
            {"_id": allocation_id},
            {"$set": {"items": list(items.values()), "updated_at": utcnow()}},
        )
        return self._out(await self._get_owned(user_id, project_id, allocation_id))

    async def decide(
        self,
        user_id: UUID,
        project_id: UUID,
        allocation_id: UUID,
        payload: DecideIn,
    ) -> AllocationOut:
        doc = await self._get_owned(user_id, project_id, allocation_id)
        self._require_proposed(doc)
        now = utcnow()
        await self.db.allocations.update_one(
            {"_id": allocation_id},
            {"$set": {"status": payload.decision, "decided_at": now, "updated_at": now}},
        )
        if payload.decision == "approved":
            await self.db.projects.update_one(
                {"_id": project_id, "user_id": user_id},
                {"$set": {"status": "approved", "updated_at": now}},
            )
        return self._out(await self._get_owned(user_id, project_id, allocation_id))
