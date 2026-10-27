"""notificaciones: the bell, its e-mail outbox, preferences and the daily digest

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-27 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0020'
down_revision: Union[str, None] = '0019'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('kind', sa.String(length=30), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('link', sa.String(length=300), nullable=True),
        sa.Column('urgent', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('read_at', sa.DateTime(), nullable=True),
        sa.Column('email_status', sa.String(length=10), server_default='none', nullable=False),
        sa.Column('email_attempts', sa.Integer(), server_default='0', nullable=False),
        sa.Column('emailed_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_notifications_id', 'notifications', ['id'])
    op.create_index('ix_notifications_user_id', 'notifications', ['user_id'])
    op.create_index('ix_notifications_created_at', 'notifications', ['created_at'])
    op.create_index('ix_notifications_email_status', 'notifications', ['email_status'])
    op.create_table(
        'notification_prefs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('kind', sa.String(length=30), nullable=False),
        sa.Column('email', sa.Boolean(), nullable=False),
        sa.UniqueConstraint('user_id', 'kind', name='uq_notification_pref'),
    )
    op.create_index('ix_notification_prefs_user_id', 'notification_prefs', ['user_id'])
    op.create_table(
        'notification_digests',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('day', sa.Date(), nullable=False),
        sa.UniqueConstraint('user_id', 'day', name='uq_notification_digest'),
    )
    op.create_index('ix_notification_digests_user_id', 'notification_digests', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_notification_digests_user_id', table_name='notification_digests')
    op.drop_table('notification_digests')
    op.drop_index('ix_notification_prefs_user_id', table_name='notification_prefs')
    op.drop_table('notification_prefs')
    op.drop_index('ix_notifications_email_status', table_name='notifications')
    op.drop_index('ix_notifications_created_at', table_name='notifications')
    op.drop_index('ix_notifications_user_id', table_name='notifications')
    op.drop_index('ix_notifications_id', table_name='notifications')
    op.drop_table('notifications')
