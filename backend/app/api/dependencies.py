from typing import Annotated

from fastapi import Depends, Request
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import Settings
from app.core.database import get_db
from app.core.security import ACCESS_COOKIE
from app.models import User
from app.services.auth import AuthService

Database = Annotated[AsyncIOMotorDatabase, Depends(get_db)]


def request_settings(request: Request) -> Settings:
    return request.app.state.settings


AppSettings = Annotated[Settings, Depends(request_settings)]


async def current_user(request: Request, db: Database, settings: AppSettings) -> User:
    return await AuthService(db, settings).current_user(request.cookies.get(ACCESS_COOKIE))


CurrentUser = Annotated[User, Depends(current_user)]