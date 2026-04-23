"""Initial schema — all tables

Revision ID: 001
Revises:
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision      = "001"
down_revision = None


def upgrade() -> None:
           
    op.create_table("users",
        sa.Column("id",              UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("email",           sa.String(255),  unique=True, nullable=False),
        sa.Column("hashed_password", sa.String(255),  nullable=True),
        sa.Column("display_name",    sa.String(100),  nullable=True),
        sa.Column("auth_provider",   sa.String(20),   server_default="email", nullable=False),
        sa.Column("google_id",       sa.String(128),  unique=True, nullable=True),
        sa.Column("avatar_url",      sa.String(500),  nullable=True),
        sa.Column("onboarding_done", sa.Boolean(),    server_default="false", nullable=False),
        sa.Column("role",            sa.String(20),   server_default="user",  nullable=False),
        sa.Column("is_verified",     sa.Boolean(),    server_default="false", nullable=False),
        sa.Column("is_active",       sa.Boolean(),    server_default="true",  nullable=False),
        sa.Column("created_at",      sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at",      sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_users_email",     "users", ["email"],     unique=True)
    op.create_index("ix_users_google_id", "users", ["google_id"], unique=True)

                         
    op.create_table("email_verifications",
        sa.Column("id",           UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id",      UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token",        sa.String(128),  unique=True, nullable=False),
        sa.Column("token_type",   sa.String(20),   server_default="verify", nullable=False),
        sa.Column("otp_code",     sa.CHAR(6),      nullable=True),
        sa.Column("otp_attempts", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("expires_at",   sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("used_at",      sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at",   sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_ev_user_id", "email_verifications", ["user_id"])
    op.create_index("ix_ev_token",   "email_verifications", ["token"], unique=True)

                             
    op.create_table("password_reset_sessions",
        sa.Column("id",           UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id",      UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token",        sa.String(128),  unique=True, nullable=False),
        sa.Column("otp_code",     sa.CHAR(6),      nullable=False),
        sa.Column("otp_attempts", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("verified",     sa.Boolean(),    server_default="false", nullable=False),
        sa.Column("expires_at",   sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("used_at",      sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at",   sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_prs_user_id", "password_reset_sessions", ["user_id"])
    op.create_index("ix_prs_token",   "password_reset_sessions", ["token"], unique=True)

                   
    op.create_table("conversations",
        sa.Column("id",             UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id",        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title",          sa.String(500), server_default="New Conversation", nullable=False),
        sa.Column("document_count", sa.Integer(),   server_default="0", nullable=False),
        sa.Column("created_at",     sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at",     sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])

               
    op.create_table("documents",
        sa.Column("id",              UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("conversation_id", UUID(as_uuid=True), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename",        sa.String(500),  nullable=False),
        sa.Column("file_path",       sa.String(1000), nullable=False),
        sa.Column("file_size",       sa.BigInteger(), nullable=True),
        sa.Column("mime_type",       sa.String(100),  nullable=True),
        sa.Column("status",          sa.String(20),   server_default="pending", nullable=False),
        sa.Column("chunk_count",     sa.Integer(),    server_default="0", nullable=False),
        sa.Column("error_msg",       sa.Text(),       nullable=True),
        sa.Column("created_at",      sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at",      sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_documents_conversation_id", "documents", ["conversation_id"])

                     
    op.create_table("document_chunks",
        sa.Column("id",          UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content",     sa.Text(),    nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("metadata",    JSONB,        server_default="{}"),
        sa.Column("created_at",  sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_chunks_document_id", "document_chunks", ["document_id"])

              
    op.create_table("messages",
        sa.Column("id",              UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("conversation_id", UUID(as_uuid=True), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role",            sa.String(20),  nullable=False),
        sa.Column("content",         sa.Text(),      nullable=False),
        sa.Column("agent_trace",     JSONB,          server_default="{}"),
        sa.Column("token_count",     sa.Integer(),   nullable=True),
        sa.Column("created_at",      sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])

                 
    op.create_table("user_quotas",
        sa.Column("id",                 UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id",            UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("requests_today",     sa.Integer(), server_default="0",  nullable=False),
        sa.Column("requests_month",     sa.Integer(), server_default="0",  nullable=False),
        sa.Column("tokens_today",       sa.Integer(), server_default="0",  nullable=False),
        sa.Column("tokens_month",       sa.Integer(), server_default="0",  nullable=False),
        sa.Column("daily_limit",        sa.Integer(), server_default="100",  nullable=False),
        sa.Column("monthly_limit",      sa.Integer(), server_default="2000", nullable=False),
        sa.Column("last_daily_reset",   sa.Date(),    server_default=sa.text("CURRENT_DATE"), nullable=False),
        sa.Column("last_monthly_reset", sa.Date(),    server_default=sa.text("DATE_TRUNC('month', CURRENT_DATE)"), nullable=False),
        sa.Column("updated_at",         sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("user_quotas")
    op.drop_table("messages")
    op.drop_table("document_chunks")
    op.drop_table("documents")
    op.drop_table("conversations")
    op.drop_table("password_reset_sessions")
    op.drop_table("email_verifications")
    op.drop_table("users")
