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