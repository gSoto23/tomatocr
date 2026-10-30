"""posibles clientes: prospects and their contact attempts

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-30 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0023'
down_revision: Union[str, None] = '0022'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'prospects',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company', sa.String(length=200), nullable=False),
        sa.Column('contact_name', sa.String(length=150), nullable=True),
        sa.Column('contact_role', sa.String(length=100), nullable=True),
        sa.Column('phone', sa.String(length=30), nullable=True),
        sa.Column('email', sa.String(length=150), nullable=True),
        sa.Column('kind', sa.String(length=30), server_default='empresa', nullable=False),
        sa.Column('motor', sa.String(length=30), nullable=True),
        sa.Column('province', sa.String(length=50), nullable=True),
        sa.Column('source', sa.String(length=20), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='por_contactar', nullable=False),
        sa.Column('next_contact_date', sa.Date(), nullable=True),
        sa.Column('last_contact_at', sa.DateTime(), nullable=True),
        sa.Column('discard_reason', sa.Text(), nullable=True),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('accounts.id'), nullable=True),
        sa.Column('opportunity_id', sa.Integer(), sa.ForeignKey('opportunities.id'), nullable=True),
        sa.Column('converted_at', sa.DateTime(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    for column in ('id', 'owner_id', 'status', 'next_contact_date'):
        op.create_index(f'ix_prospects_{column}', 'prospects', [column])
    op.create_table(
        'prospect_attempts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('prospect_id', sa.Integer(), sa.ForeignKey('prospects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('channel', sa.String(length=20), server_default='llamada', nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('happened_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_prospect_attempts_id', 'prospect_attempts', ['id'])
    op.create_index('ix_prospect_attempts_prospect_id', 'prospect_attempts', ['prospect_id'])


def downgrade() -> None:
    op.drop_index('ix_prospect_attempts_prospect_id', table_name='prospect_attempts')
    op.drop_index('ix_prospect_attempts_id', table_name='prospect_attempts')
    op.drop_table('prospect_attempts')
    for column in ('next_contact_date', 'status', 'owner_id', 'id'):
        op.drop_index(f'ix_prospects_{column}', table_name='prospects')
    op.drop_table('prospects')
