"""a task for several people: task_assignees, each one marks it done

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-13 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0018'
down_revision: Union[str, None] = '0017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'task_assignees',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('task_id', sa.Integer(), sa.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('done_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('task_id', 'user_id', name='uq_task_assignee'),
    )
    op.create_index('ix_task_assignees_task_id', 'task_assignees', ['task_id'])
    op.create_index('ix_task_assignees_user_id', 'task_assignees', ['user_id'])
    # Every existing task keeps its one person and whether it was done.
    op.execute("INSERT INTO task_assignees (task_id, user_id, done_at) SELECT id, assignee_id, done_at FROM tasks")
    with op.batch_alter_table('tasks') as batch:
        batch.drop_index('ix_tasks_assignee_id')
        batch.drop_column('assignee_id')
        batch.drop_column('done_at')


def downgrade() -> None:
    # Back to one person per task: the first one assigned (and their done mark) stays.
    with op.batch_alter_table('tasks') as batch:
        batch.add_column(sa.Column('assignee_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('done_at', sa.DateTime(), nullable=True))
    op.execute("""UPDATE tasks SET
        assignee_id = (SELECT a.user_id FROM task_assignees a WHERE a.task_id = tasks.id ORDER BY a.id LIMIT 1),
        done_at = (SELECT a.done_at FROM task_assignees a WHERE a.task_id = tasks.id ORDER BY a.id LIMIT 1)""")
    op.execute("DELETE FROM tasks WHERE assignee_id IS NULL")
    with op.batch_alter_table('tasks') as batch:
        batch.alter_column('assignee_id', existing_type=sa.Integer(), nullable=False)
        batch.create_foreign_key('tasks_assignee_id_fkey', 'users', ['assignee_id'], ['id'])
        batch.create_index('ix_tasks_assignee_id', ['assignee_id'])
    op.drop_index('ix_task_assignees_user_id', table_name='task_assignees')
    op.drop_index('ix_task_assignees_task_id', table_name='task_assignees')
    op.drop_table('task_assignees')
