"""archive tasks and sedes

Editing a project used to delete and recreate its tasks, sedes and budget lines.
On PostgreSQL that fails once reports, calendar entries or invoices use them
(foreign keys). Now they are updated in place; a task or sede that is removed
but already used is archived instead of deleted, so old reports keep it.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-27 17:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0008'
down_revision: Union[str, None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('project_tasks', sa.Column('archived_at', sa.DateTime(), nullable=True))
    op.add_column('project_locations', sa.Column('archived_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('project_locations', 'archived_at')
    op.drop_column('project_tasks', 'archived_at')
