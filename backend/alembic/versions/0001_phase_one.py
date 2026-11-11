"""Phase 1 identity, sessions, dashboard foundations, and pgvector extension.

Revision ID: 0001_phase_one
Revises: None
"""

import sqlalchemy as sa

from alembic import op

revision = "0001_phase_one"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_refresh_tokens"),
        sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_refresh_tokens_user_id_users", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"])
    op.create_table(
        "knowledge_bases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_bases"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_knowledge_bases_user_id_users", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_knowledge_bases_user_id", "knowledge_bases", ["user_id"])
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("knowledge_base_id", sa.Uuid(), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("mime_type", sa.String(127), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), server_default="queued", nullable=False),
        sa.Column("chunk_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
        sa.CheckConstraint("file_size >= 0", name=op.f("ck_documents_file_size_nonnegative")),
        sa.CheckConstraint("chunk_count >= 0", name=op.f("ck_documents_chunk_count_nonnegative")),
        sa.CheckConstraint(
            "status IN ('queued', 'processing', 'ready', 'failed')",
            name=op.f("ck_documents_status"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_documents_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_bases.id"],
            name="fk_documents_knowledge_base_id_knowledge_bases",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_documents_user_id", "documents", ["user_id"])
    op.create_index("ix_documents_knowledge_base_id", "documents", ["knowledge_base_id"])
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("knowledge_base_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_conversations"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_conversations_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_bases.id"],
            name="fk_conversations_knowledge_base_id_knowledge_bases",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])
    op.create_index("ix_conversations_knowledge_base_id", "conversations", ["knowledge_base_id"])
    op.create_table(
        "ai_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ai_requests"),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'failed', 'cancelled')",
            name=op.f("ck_ai_requests_status"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_ai_requests_user_id_users", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_ai_requests_user_id", "ai_requests", ["user_id"])
    op.create_table(
        "activity_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_activity_logs"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_activity_logs_user_id_users", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_activity_logs_user_id", "activity_logs", ["user_id"])
    op.create_index("ix_activity_logs_user_created", "activity_logs", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_table("activity_logs")
    op.drop_table("ai_requests")
    op.drop_table("conversations")
    op.drop_table("documents")
    op.drop_table("knowledge_bases")
    op.drop_table("refresh_tokens")
    op.drop_table("users")
    # The shared extension is intentionally retained; dropping it can destroy other schemas.
