from dataclasses import dataclass
from uuid import UUID
from datetime import timedelta

from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import Settings
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    decode_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)
from app.models import RefreshToken, User
from app.models.base import utcnow
from app.repositories.auth import AuthRepository
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    UpdateProfileRequest,
)


@dataclass(frozen=True)
class AuthResult:
    user: User
    access_token: str
    refresh_token: str


class AuthService:
    def __init__(self, db: AsyncIOMotorDatabase, settings: Settings):
        self.db = db
        self.settings = settings
        self.repository = AuthRepository(db)

    def _result(self, user: User, session: RefreshToken, refresh: str) -> AuthResult:
        return AuthResult(user, create_access_token(user.id, session.id, self.settings), refresh)

    async def _new_session(self, user: User) -> AuthResult:
        refresh = new_refresh_token()
        session = await self.repository.create_session(
            user.id,
            hash_refresh_token(refresh),
            utcnow() + timedelta(days=self.settings.refresh_token_days),
        )
        return self._result(user, session, refresh)

    async def register(self, payload: RegisterRequest) -> AuthResult:
        if await self.repository.user_by_email(str(payload.email)):
            raise HTTPException(status.HTTP_409_CONFLICT, "Email is already registered")
        try:
            user = await self.repository.create_user(
                email=str(payload.email),
                name=payload.name,
                password_hash=hash_password(payload.password.get_secret_value()),
            )
            result = await self._new_session(user)
            await self.repository.record_activity(user.id, "auth.register", "Account created")
            return result
        except Exception as e:
            # Handle duplicate key error from MongoDB
            if "duplicate key" in str(e).lower() or "E11000" in str(e):
                if await self.repository.user_by_email(str(payload.email)):
                    raise HTTPException(
                        status.HTTP_409_CONFLICT, "Email is already registered"
                    ) from None
            raise

    async def update_profile(
        self, user_id: UUID, payload: UpdateProfileRequest
    ) -> User:
        user = await self.repository.update_name(user_id, payload.name)
        if user is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "User no longer exists"
            )
        await self.repository.record_activity(
            user.id, "auth.profile_update", "Profile name updated"
        )
        return user

    async def login(self, payload: LoginRequest) -> AuthResult:
        user = await self.repository.user_by_email(str(payload.email))
        valid = verify_password(
            payload.password.get_secret_value(),
            user.password_hash if user else DUMMY_PASSWORD_HASH,
        )
        if not valid or user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
        result = await self._new_session(user)
        await self.repository.record_activity(user.id, "auth.login", "Signed in")
        return result

    async def refresh(self, token: str | None) -> AuthResult:
        if not token or len(token) > 512:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")
        now = utcnow()
        replacement = new_refresh_token()
        session = await self.repository.rotate_session(
            hash_refresh_token(token),
            hash_refresh_token(replacement),
            now,
            now + timedelta(days=self.settings.refresh_token_days),
        )
        if session is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")
        user = await self.db.users.find_one({"_id": session.user_id})
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")
        user_model = User(**user)
        result = self._result(user_model, session, replacement)
        return result

    async def current_user(self, access: str | None) -> User:
        identity = decode_access_token(access, self.settings) if access else None
        user = (
            await self.repository.active_user(*identity, utcnow())
            if identity
            else None
        )
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
        return user

    async def logout(self, access: str | None, refresh: str | None) -> None:
        identity = (
            decode_access_token(access, self.settings, allow_expired=True) if access else None
        )
        await self.repository.revoke_sessions(
            utcnow(), hash_refresh_token(refresh) if refresh else None, identity
        )