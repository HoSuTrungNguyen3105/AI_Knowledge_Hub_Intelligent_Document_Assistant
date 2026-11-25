from datetime import datetime
from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models import ActivityLog, RefreshToken, User
from app.models.base import utcnow


class AuthRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.users = db.users
        self.refresh_tokens = db.refresh_tokens
        self.activity_logs = db.activity_logs

    async def user_by_email(self, email: str) -> User | None:
        doc = await self.users.find_one({"email": email})
        if doc:
            return User(**doc)
        return None

    async def create_user(self, *, email: str, name: str, password_hash: str) -> User:
        user_id = User.generate_id()
        now = utcnow()
        user_doc = {
            "_id": user_id,
            "email": email,
            "name": name,
            "password_hash": password_hash,
            "created_at": now,
        }
        await self.users.insert_one(user_doc)
        # MongoDB stores datetimes at millisecond precision; return the persisted
        # document so the register response matches subsequent reads exactly.
        stored = await self.users.find_one({"_id": user_id})
        return User(**stored)

    async def update_name(self, user_id: UUID, name: str) -> User | None:
        doc = await self.users.find_one_and_update(
            {"_id": user_id},
            {"$set": {"name": name}},
            return_document=True,
        )
        return User(**doc) if doc else None

    async def create_session(
        self, user_id: UUID, token_hash: str, expires_at: datetime
    ) -> RefreshToken:
        session_id = RefreshToken.generate_id()
        now = utcnow()
        session_doc = {
            "_id": session_id,
            "user_id": user_id,
            "token_hash": token_hash,
            "expires_at": expires_at,
            "revoked_at": None,
            "created_at": now,
        }
        await self.refresh_tokens.insert_one(session_doc)
        return RefreshToken(**session_doc)

    async def record_activity(self, user_id: UUID, action: str, description: str) -> None:
        log_id = ActivityLog.generate_id()
        now = utcnow()
        log_doc = {
            "_id": log_id,
            "user_id": user_id,
            "action": action,
            "description": description,
            "created_at": now,
        }
        await self.activity_logs.insert_one(log_doc)

    async def active_user(
        self, user_id: UUID, session_id: UUID, now: datetime
    ) -> User | None:
        session = await self.refresh_tokens.find_one(
            {
                "_id": session_id,
                "user_id": user_id,
                "revoked_at": None,
                "expires_at": {"$gt": now},
            }
        )
        if not session:
            return None
        user = await self.users.find_one({"_id": user_id})
        if not user:
            return None
        return User(**user)

    async def rotate_session(
        self, old_hash: str, new_hash: str, now: datetime, expires_at: datetime
    ) -> RefreshToken | None:
        result = await self.refresh_tokens.find_one_and_update(
            {
                "token_hash": old_hash,
                "revoked_at": None,
                "expires_at": {"$gt": now},
            },
            {"$set": {"token_hash": new_hash, "expires_at": expires_at}},
            return_document=True,
        )
        if result:
            return RefreshToken(**result)
        return None

    async def revoke_sessions(
        self,
        now: datetime,
        refresh_hash: str | None,
        access_identity: tuple[UUID, UUID] | None,
    ) -> None:
        predicates = []
        if refresh_hash:
            predicates.append({"token_hash": refresh_hash})
        if access_identity:
            user_id, session_id = access_identity
            predicates.append({"_id": session_id, "user_id": user_id})

        if predicates:
            await self.refresh_tokens.update_many(
                {"$or": predicates, "revoked_at": None}, {"$set": {"revoked_at": now}}
            )