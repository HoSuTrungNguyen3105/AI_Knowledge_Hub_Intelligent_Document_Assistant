"""Seed 50 demo employees into the caller's workforce (test data for
the Workforce + Projects features).

The employee set lives in app/seed_data/workforce_employees.json and is
validated through ResourceCreate before anything is written, so the
seed can never create a resource the API itself would reject. Safety
rules mirror the demo seed (services/seed.py):

- Only runs when APP_ENV is development or demo; production is refused
  with `seed_disabled`. Nothing runs automatically at startup.
- Idempotent by name within the caller's own resources: an existing
  resource with the same name is skipped, never overwritten.
- Seeded records are flagged `is_demo: True`; removal deletes only
  those, so real resources are never touched.
"""

import json
from pathlib import Path
from uuid import UUID, uuid4

from app.core.config import Settings
from app.models.base import utcnow
from app.schemas.resources import ResourceCreate
from app.schemas.seed import WorkforceSeedOut, WorkforceSeedRemoveOut
from app.services.ai.base_provider import ProviderError

DATA_FILE = (
    Path(__file__).resolve().parent.parent / "seed_data" / "workforce_employees.json"
)


def load_employees() -> list[ResourceCreate]:
    raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return [ResourceCreate.model_validate(item) for item in raw]


class WorkforceSeedService:
    def __init__(self, db, settings: Settings):
        self.db = db
        self.settings = settings

    def _require_enabled(self) -> None:
        if self.settings.app_env not in {"development", "demo"}:
            raise ProviderError("seed_disabled")

    async def apply(self, user_id: UUID) -> WorkforceSeedOut:
        self._require_enabled()
        employees = load_employees()
        existing = {
            doc["name"]
            async for doc in self.db.resources.find({"user_id": user_id}, {"name": 1})
        }
        created = skipped = 0
        now = utcnow()
        for employee in employees:
            if employee.name in existing:
                skipped += 1
                continue
            doc = {
                "_id": uuid4(),
                "user_id": user_id,
                "type": employee.type,
                "name": employee.name,
                "role": employee.role,
                "skills": [skill.model_dump() for skill in employee.skills],
                "availability_status": employee.availability_status,
                "cost_per_hour": employee.cost_per_hour,
                "notes": employee.notes,
                "human": employee.human.model_dump() if employee.human else None,
                "ai": employee.ai.model_dump() if employee.ai else None,
                "is_demo": True,
                "created_at": now,
                "updated_at": now,
            }
            await self.db.resources.insert_one(doc)
            created += 1
        return WorkforceSeedOut(created=created, skipped=skipped, total=len(employees))

    async def remove(self, user_id: UUID) -> WorkforceSeedRemoveOut:
        self._require_enabled()
        result = await self.db.resources.delete_many(
            {"user_id": user_id, "is_demo": True}
        )
        return WorkforceSeedRemoveOut(removed=result.deleted_count)
