from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from app.models import ActivityLog, RefreshToken, User


class AuthRepository:
    def __init__(self, db: Session):
        self.db = db

    def user_by_email(self, email: str) -> User | None:
        return self.db.scalar(select(User).where(User.email == email))

    def create_user(self, *, email: str, name: str, password_hash: str) -> User:
        user = User(email=email, name=name, password_hash=password_hash)
        self.db.add(user)
        self.db.flush()
        return user

    def create_session(self, user_id: UUID, token_hash: str, expires_at: datetime) -> RefreshToken:
        session = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self.db.add(session)
        self.db.flush()
        return session

    def record_activity(self, user_id: UUID, action: str, description: str) -> None:
        self.db.add(ActivityLog(user_id=user_id, action=action, description=description))

    def active_user(self, user_id: UUID, session_id: UUID, now: datetime) -> User | None:
        return self.db.scalar(
            select(User)
            .join(RefreshToken, RefreshToken.user_id == User.id)
            .where(
                User.id == user_id,
                RefreshToken.id == session_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
        )

    def rotate_session(
        self, old_hash: str, new_hash: str, now: datetime, expires_at: datetime
    ) -> RefreshToken | None:
        # One conditional UPDATE, not a read followed by a write. Concurrent replays
        # cannot both win, including on PostgreSQL's READ COMMITTED isolation level.
        return self.db.scalar(
            update(RefreshToken)
            .where(
                RefreshToken.token_hash == old_hash,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
            .values(token_hash=new_hash, expires_at=expires_at)
            .returning(RefreshToken)
        )

    def revoke_sessions(
        self,
        now: datetime,
        refresh_hash: str | None,
        access_identity: tuple[UUID, UUID] | None,
    ) -> None:
        predicates = []
        if refresh_hash:
            predicates.append(RefreshToken.token_hash == refresh_hash)
        if access_identity:
            user_id, session_id = access_identity
            predicates.append(and_(RefreshToken.id == session_id, RefreshToken.user_id == user_id))
        if predicates:
            self.db.execute(
                update(RefreshToken)
                .where(or_(*predicates), RefreshToken.revoked_at.is_(None))
                .values(revoked_at=now)
            )
