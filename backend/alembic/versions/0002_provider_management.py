"""Owner-bound encrypted provider credentials and model-listing cache only.

Revision ID: 0002_provider_management
Revises: 0001_phase_one
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0002_provider_management"
down_revision = "0001_phase_one"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_provider_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("encrypted_api_key", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("default_model", sa.String(512), nullable=True),
        sa.Column("connection_status", sa.String(20), server_default="untested", nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("models_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_provider_credentials"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_user_provider_credentials_user_id_users",
        ),
        sa.UniqueConstraint("user_id", "provider", name="uq_user_provider_credentials_user_id"),
        sa.CheckConstraint(
            "connection_status IN ('untested', 'connected', 'error')",
            name="ck_user_provider_credentials_status",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_user_provider_credentials_revision_positive"),
    )
    op.create_index(
        "ix_user_provider_credentials_user_id", "user_provider_credentials", ["user_id"]
    )
    op.create_table(
        "ai_models",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("credential_id", sa.Uuid(), nullable=False),
        sa.Column("model_id", sa.String(512), nullable=False),
        sa.Column("display_name", sa.String(1024), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "capabilities", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
        ),
        sa.Column("input_token_limit", sa.Integer(), nullable=True),
        sa.Column("output_token_limit", sa.Integer(), nullable=True),
        sa.Column("capability_source", sa.String(32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ai_models"),
        sa.ForeignKeyConstraint(
            ["credential_id"],
            ["user_provider_credentials.id"],
            ondelete="CASCADE",
            name="fk_ai_models_credential_id_user_provider_credentials",
        ),
        sa.UniqueConstraint("credential_id", "model_id", name="uq_ai_models_credential_id"),
        sa.CheckConstraint("input_token_limit >= 0", name="ck_ai_models_input_limit_nonnegative"),
        sa.CheckConstraint("output_token_limit >= 0", name="ck_ai_models_output_limit_nonnegative"),
    )
    op.create_index("ix_ai_models_credential_id", "ai_models", ["credential_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_models_credential_id", table_name="ai_models")
    op.drop_table("ai_models")
    op.drop_index("ix_user_provider_credentials_user_id", table_name="user_provider_credentials")
    op.drop_table("user_provider_credentials")
