"""proyectos: terminar un proyecto (el contrato no se renueva)

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-12 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0030'
down_revision: Union[str, None] = '0029'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('projects') as batch:
        batch.add_column(sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column('ended_by_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('end_reason', sa.Text(), nullable=True))
        batch.create_foreign_key('fk_projects_ended_by_id_users', 'users', ['ended_by_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('projects') as batch:
        batch.drop_constraint('fk_projects_ended_by_id_users', type_='foreignkey')
        batch.drop_column('end_reason')
        batch.drop_column('ended_by_id')
        batch.drop_column('ended_at')
