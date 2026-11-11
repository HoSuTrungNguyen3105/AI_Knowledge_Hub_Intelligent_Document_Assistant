from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdentityMixin, UpdatedMixin, UTCDateTime


class User(IdentityMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    sessions: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class RefreshToken(IdentityMixin, Base):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    user: Mapped[User] = relationship(back_populates="sessions")


class KnowledgeBase(IdentityMixin, UpdatedMixin, Base):
    __tablename__ = "knowledge_bases"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    documents: Mapped[list["Document"]] = relationship(
        back_populates="knowledge_base", cascade="all, delete-orphan", passive_deletes=True
    )


class Document(IdentityMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("file_size >= 0", name="file_size_nonnegative"),
        CheckConstraint("chunk_count >= 0", name="chunk_count_nonnegative"),
        CheckConstraint("status IN ('queued', 'processing', 'ready', 'failed')", name="status"),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    knowledge_base_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(127), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", server_default="queued")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text)
    knowledge_base: Mapped[KnowledgeBase] = relationship(back_populates="documents")


class Conversation(IdentityMixin, UpdatedMixin, Base):
    __tablename__ = "conversations"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    knowledge_base_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)


class AIRequest(IdentityMixin, Base):
    __tablename__ = "ai_requests"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'completed', 'failed', 'cancelled')", name="status"),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)


class ActivityLog(IdentityMixin, Base):
    __tablename__ = "activity_logs"
    __table_args__ = (Index("ix_activity_logs_user_created", "user_id", "created_at"),)

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
