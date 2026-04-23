"""Admin enhancements

Revision ID: 8c57eb4c9b80
Revises: 446b55425f1d
Create Date: 2026-04-23 06:11:09.036156

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '8c57eb4c9b80'
down_revision: Union[str, None] = '446b55425f1d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
                                                                 
    op.create_table('system_settings',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('key', sa.String(length=255), nullable=False),
    sa.Column('value', sa.JSON(), nullable=False),
    sa.Column('description', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_system_settings_key'), 'system_settings', ['key'], unique=True)
    op.create_table('admin_audit_logs',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('admin_id', sa.UUID(), nullable=False),
    sa.Column('target_entity_type', sa.String(length=50), nullable=False),
    sa.Column('target_entity_id', sa.UUID(), nullable=False),
    sa.Column('action', sa.String(length=50), nullable=False),
    sa.Column('changes', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['admin_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_admin_audit_logs_admin_id'), 'admin_audit_logs', ['admin_id'], unique=False)
    op.create_index(op.f('ix_admin_audit_logs_target_entity_id'), 'admin_audit_logs', ['target_entity_id'], unique=False)
    op.add_column('users', sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False))
                                  


def downgrade() -> None:
                                                                 
    op.drop_column('users', 'is_deleted')
    op.drop_index(op.f('ix_admin_audit_logs_target_entity_id'), table_name='admin_audit_logs')
    op.drop_index(op.f('ix_admin_audit_logs_admin_id'), table_name='admin_audit_logs')
    op.drop_table('admin_audit_logs')
    op.drop_index(op.f('ix_system_settings_key'), table_name='system_settings')
    op.drop_table('system_settings')
                                  
