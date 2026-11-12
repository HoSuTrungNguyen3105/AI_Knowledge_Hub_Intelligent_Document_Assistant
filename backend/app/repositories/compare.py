from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models import Comparison
from app.models.base import utcnow
from app.models.entities import ComparisonRun


class CompareRepository:
    """Owner-scoped persistence for comparisons with embedded runs/synthesis."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.comparisons = db.comparisons

    async def create(
        self,
        user_id: UUID,
        *,
        title: str,
        prompt: str,
        system_prompt: str | None,
        temperature: float | None,
        max_output_tokens: int | None,
        runs: list[ComparisonRun],
    ) -> Comparison:
        now = utcnow()
        doc = {
            "_id": Comparison.generate_id(),
            "user_id": user_id,
            "title": title,
            "prompt": prompt,
            "system_prompt": system_prompt,
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
            "runs": [run.model_dump() for run in runs],
            "synthesis": None,
            "created_at": now,
            "updated_at": now,
        }
        await self.comparisons.insert_one(doc)
        return Comparison(**doc)

    async def list(self, user_id: UUID) -> list[Comparison]:
        cursor = self.comparisons.find({"user_id": user_id}).sort("updated_at", -1)
        return [Comparison(**doc) async for doc in cursor]

    async def get(self, user_id: UUID, comparison_id: UUID) -> Comparison | None:
        doc = await self.comparisons.find_one({"_id": comparison_id, "user_id": user_id})
        return Comparison(**doc) if doc else None

    async def delete(self, user_id: UUID, comparison_id: UUID) -> bool:
        result = await self.comparisons.delete_one({"_id": comparison_id, "user_id": user_id})
        return result.deleted_count > 0

    async def update_run(
        self, user_id: UUID, comparison_id: UUID, run_id: UUID, values: dict
    ) -> None:
        updates = {f"runs.$[r].{key}": value for key, value in values.items()}
        updates["updated_at"] = utcnow()
        await self.comparisons.update_one(
            {"_id": comparison_id, "user_id": user_id},
            {"$set": updates},
            array_filters=[{"r.id": run_id}],
        )

    async def set_synthesis(
        self, user_id: UUID, comparison_id: UUID, synthesis: dict
    ) -> None:
        await self.comparisons.update_one(
            {"_id": comparison_id, "user_id": user_id},
            {"$set": {"synthesis": synthesis, "updated_at": utcnow()}},
        )

    async def touch(self, user_id: UUID, comparison_id: UUID) -> None:
        await self.comparisons.update_one(
            {"_id": comparison_id, "user_id": user_id},
            {"$set": {"updated_at": utcnow()}},
        )