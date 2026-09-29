"""Dashboard tasks and "ya lo vi" marks on alerts

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-29 22:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0014'
down_revision: Union[str, None] = '0013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tasks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('priority', sa.String(length=10), server_default='normal', nullable=False),
        sa.Column('assignee_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('done_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_tasks_id', 'tasks', ['id'])
    op.create_index('ix_tasks_due_date', 'tasks', ['due_date'])
    op.create_index('ix_tasks_assignee_id', 'tasks', ['assignee_id'])
    op.create_table(
        'alert_acks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('key', sa.String(length=60), nullable=False),
        sa.Column('items', sa.Text(), nullable=False),
        sa.Column('acked_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('user_id', 'key', name='uq_alert_ack_user_key'),
    )
    op.create_index('ix_alert_acks_user_id', 'alert_acks', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_alert_acks_user_id', table_name='alert_acks')
    op.drop_table('alert_acks')
    op.drop_index('ix_tasks_assignee_id', table_name='tasks')
    op.drop_index('ix_tasks_due_date', table_name='tasks')
    op.drop_index('ix_tasks_id', table_name='tasks')
    op.drop_table('tasks')
