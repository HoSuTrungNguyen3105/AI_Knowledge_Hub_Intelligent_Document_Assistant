from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import Database
from app.models import User

router = APIRouter(tags=["Health"])


@router.get("/health")
def health(db: Database) -> dict[str, str]:
    try:
        # Also verifies that migrations were applied, not just that a socket is open.
        db.execute(select(User.id).limit(1))
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=503, detail="Database unavailable") from None
    return {"status": "ok"}
