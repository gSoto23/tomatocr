"""proyectos: vendedor encargado (supervisa el proyecto a nivel administrativo y gana la comisión)

Revision ID: 0031
Revises: 0030
Create Date: 2026-11-12 16:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0031'
down_revision: Union[str, None] = '0030'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('projects') as batch:
        batch.add_column(sa.Column('seller_id', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_projects_seller_id_users', 'users', ['seller_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('projects') as batch:
        batch.drop_constraint('fk_projects_seller_id_users', type_='foreignkey')
        batch.drop_column('seller_id')
