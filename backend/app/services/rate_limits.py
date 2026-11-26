"""Persistence for provider-reported rate-limit snapshots.

Snapshots live in the ``provider_rate_limits`` collection, one
document per (user, provider, model), overwritten by every newer
provider response. The numbers are always the provider's own —
MindFlow never computes or estimates quota.
"""

import logging
from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.base import utcnow
from app.services.ai.rate_limits import latest_rate_limit

logger = logging.getLogger(__name__)

COLLECTION = "provider_rate_limits"


async def persist_rate_limit_snapshot(
    db: AsyncIOMotorDatabase, user_id: UUID, provider: str, model: str
) -> None:
    """Attach the snapshot captured during the call being recorded.

    Best-effort by design: quota display must never break request
    accounting, so failures are logged and swallowed.
    """
    try:
        snapshot = latest_rate_limit(provider, model)
        if snapshot is None:
            return
        now = utcnow()
        await db[COLLECTION].update_one(
            {"user_id": user_id, "provider": provider, "model": model},
            {
                "$set": {**snapshot, "captured_at": now},
                "$setOnInsert": {
                    "user_id": user_id,
                    "provider": provider,
                    "model": model,
                },
            },
            upsert=True,
        )
    except Exception:
        logger.warning("rate limit snapshot persist failed", exc_info=True)


async def list_rate_limit_snapshots(
    db: AsyncIOMotorDatabase, user_id: UUID
) -> list[dict]:
    cursor = db[COLLECTION].find({"user_id": user_id}).sort("captured_at", -1)
    return [doc async for doc in cursor]
