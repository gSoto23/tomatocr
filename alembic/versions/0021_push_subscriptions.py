"""app para celular: phones with notifications on (web push) and the push outbox

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-27 16:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0021'
down_revision: Union[str, None] = '0020'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'push_subscriptions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('endpoint', sa.Text(), nullable=False),
        sa.Column('p256dh', sa.String(length=200), nullable=False),
        sa.Column('auth', sa.String(length=100), nullable=False),
        sa.Column('user_agent', sa.String(length=300), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('endpoint', name='uq_push_subscriptions_endpoint'),
    )
    op.create_index('ix_push_subscriptions_user_id', 'push_subscriptions', ['user_id'])
    op.add_column('notifications', sa.Column('push_status', sa.String(length=10), server_default='none', nullable=False))
    op.add_column('notifications', sa.Column('push_attempts', sa.Integer(), server_default='0', nullable=False))
    op.add_column('notifications', sa.Column('pushed_at', sa.DateTime(), nullable=True))
    op.create_index('ix_notifications_push_status', 'notifications', ['push_status'])


def downgrade() -> None:
    op.drop_index('ix_notifications_push_status', table_name='notifications')
    op.drop_column('notifications', 'pushed_at')
    op.drop_column('notifications', 'push_attempts')
    op.drop_column('notifications', 'push_status')
    op.drop_index('ix_push_subscriptions_user_id', table_name='push_subscriptions')
    op.drop_table('push_subscriptions')
