"""días que no ocupan bitácora: dejan de contar en «días trabajados sin bitácora»

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-12 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0029'
down_revision: Union[str, None] = '0028'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'daily_log_exemptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('reason', sa.String(length=200), nullable=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'date', name='uq_log_exemption_project_date'),
    )
    op.create_index('ix_daily_log_exemptions_id', 'daily_log_exemptions', ['id'])
    op.create_index('ix_daily_log_exemptions_project_id', 'daily_log_exemptions', ['project_id'])
    op.create_index('ix_daily_log_exemptions_date', 'daily_log_exemptions', ['date'])


def downgrade() -> None:
    op.drop_index('ix_daily_log_exemptions_date', table_name='daily_log_exemptions')
    op.drop_index('ix_daily_log_exemptions_project_id', table_name='daily_log_exemptions')
    op.drop_index('ix_daily_log_exemptions_id', table_name='daily_log_exemptions')
    op.drop_table('daily_log_exemptions')
