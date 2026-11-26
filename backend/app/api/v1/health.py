from fastapi import APIRouter, HTTPException

from app.api.dependencies import Database

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health(db: Database) -> dict[str, str]:
    try:
        await db.command("ping")
    except Exception:
        raise HTTPException(status_code=503, detail="Database unavailable") from None
    return {"status": "ok"}

@router.get("/health/ping")
async def health_ping() -> dict[str, str]:
    """Lightweight liveness probe for the frontend wake-up banner.

    No auth and no database touch: it answers as soon as the process
    itself is serving, which is exactly the signal that separates
    "server is still starting" (Render cold start) from "server is
    down". The deep check above stays at /health for monitoring.
    """
    return {"status": "ok"}
