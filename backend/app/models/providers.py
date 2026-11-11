from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdentityMixin, UpdatedMixin, UTCDateTime


class UserProviderCredential(IdentityMixin, UpdatedMixin, Base):
    __tablename__ = "user_provider_credentials"
    __table_args__ = (
        UniqueConstraint("user_id", "provider"),
        CheckConstraint("connection_status IN ('untested', 'connected', 'error')", name="status"),
        CheckConstraint("revision >= 1", name="revision_positive"),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    encrypted_api_key: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    default_model: Mapped[str | None] = mapped_column(String(512))
    connection_status: Mapped[str] = mapped_column(
        String(20), default="untested", server_default="untested"
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    models_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class AIModel(IdentityMixin, Base):
    __tablename__ = "ai_models"
    __table_args__ = (
        UniqueConstraint("credential_id", "model_id"),
        CheckConstraint("input_token_limit >= 0", name="input_limit_nonnegative"),
        CheckConstraint("output_token_limit >= 0", name="output_limit_nonnegative"),
    )

    credential_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_provider_credentials.id", ondelete="CASCADE"), index=True
    )
    model_id: Mapped[str] = mapped_column(String(512), nullable=False)
    display_name: Mapped[str] = mapped_column(String(1024), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    capabilities: Mapped[dict[str, bool | None]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False
    )
    input_token_limit: Mapped[int | None] = mapped_column(Integer)
    output_token_limit: Mapped[int | None] = mapped_column(Integer)
    capability_source: Mapped[str] = mapped_column(String(32), nullable=False)
