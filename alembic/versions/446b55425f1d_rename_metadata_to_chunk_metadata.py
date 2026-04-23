"""rename metadata to chunk_metadata

Revision ID: 446b55425f1d
Revises: 001
Create Date: 2026-04-18 00:21:20.733494

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '446b55425f1d'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
                                                                 
    op.add_column('document_chunks', sa.Column('chunk_metadata', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False))
    op.drop_index(op.f('ix_chunks_document_id'), table_name='document_chunks')
    op.create_index(op.f('ix_document_chunks_document_id'), 'document_chunks', ['document_id'], unique=False)
    op.drop_column('document_chunks', 'metadata')
    op.drop_constraint(op.f('email_verifications_token_key'), 'email_verifications', type_='unique')
    op.drop_index(op.f('ix_ev_token'), table_name='email_verifications')
    op.drop_index(op.f('ix_ev_user_id'), table_name='email_verifications')
    op.create_index(op.f('ix_email_verifications_token'), 'email_verifications', ['token'], unique=True)
    op.create_index(op.f('ix_email_verifications_user_id'), 'email_verifications', ['user_id'], unique=False)
    op.alter_column('messages', 'agent_trace',
               existing_type=postgresql.JSONB(astext_type=sa.Text()),
               nullable=False,
               existing_server_default=sa.text("'{}'::jsonb"))
    op.drop_index(op.f('ix_prs_token'), table_name='password_reset_sessions')
    op.drop_index(op.f('ix_prs_user_id'), table_name='password_reset_sessions')
    op.drop_constraint(op.f('password_reset_sessions_token_key'), 'password_reset_sessions', type_='unique')
    op.create_index(op.f('ix_password_reset_sessions_token'), 'password_reset_sessions', ['token'], unique=True)
    op.create_index(op.f('ix_password_reset_sessions_user_id'), 'password_reset_sessions', ['user_id'], unique=False)
    op.drop_constraint(op.f('users_email_key'), 'users', type_='unique')
    op.drop_constraint(op.f('users_google_id_key'), 'users', type_='unique')
                                  


def downgrade() -> None:
                                                                 
    op.create_unique_constraint(op.f('users_google_id_key'), 'users', ['google_id'], postgresql_nulls_not_distinct=False)
    op.create_unique_constraint(op.f('users_email_key'), 'users', ['email'], postgresql_nulls_not_distinct=False)
    op.drop_index(op.f('ix_password_reset_sessions_user_id'), table_name='password_reset_sessions')
    op.drop_index(op.f('ix_password_reset_sessions_token'), table_name='password_reset_sessions')
    op.create_unique_constraint(op.f('password_reset_sessions_token_key'), 'password_reset_sessions', ['token'], postgresql_nulls_not_distinct=False)
    op.create_index(op.f('ix_prs_user_id'), 'password_reset_sessions', ['user_id'], unique=False)
    op.create_index(op.f('ix_prs_token'), 'password_reset_sessions', ['token'], unique=True)
    op.alter_column('messages', 'agent_trace',
               existing_type=postgresql.JSONB(astext_type=sa.Text()),
               nullable=True,
               existing_server_default=sa.text("'{}'::jsonb"))
    op.drop_index(op.f('ix_email_verifications_user_id'), table_name='email_verifications')
    op.drop_index(op.f('ix_email_verifications_token'), table_name='email_verifications')
    op.create_index(op.f('ix_ev_user_id'), 'email_verifications', ['user_id'], unique=False)
    op.create_index(op.f('ix_ev_token'), 'email_verifications', ['token'], unique=True)
    op.create_unique_constraint(op.f('email_verifications_token_key'), 'email_verifications', ['token'], postgresql_nulls_not_distinct=False)
    op.add_column('document_chunks', sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), autoincrement=False, nullable=True))
    op.drop_index(op.f('ix_document_chunks_document_id'), table_name='document_chunks')
    op.create_index(op.f('ix_chunks_document_id'), 'document_chunks', ['document_id'], unique=False)
    op.drop_column('document_chunks', 'chunk_metadata')
                                  
