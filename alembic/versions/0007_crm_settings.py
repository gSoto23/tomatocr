"""crm settings

Pilot in the system (decision of 27/09/2026): the funnel counts only new
opportunities created inside a period that admin can edit. Seeds the pilot,
15/10/2026 to 15/12/2026.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-27 15:10:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: Union[str, None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    table = op.create_table(
        'crm_settings',
        sa.Column('key', sa.String(length=50), nullable=False),
        sa.Column('value', sa.String(length=200), nullable=True),
        sa.PrimaryKeyConstraint('key'),
    )
    op.bulk_insert(table, [
        {'key': 'funnel_name', 'value': 'Piloto'},
        {'key': 'funnel_start', 'value': '2026-10-15'},
        {'key': 'funnel_end', 'value': '2026-12-15'},
    ])


def downgrade() -> None:
    op.drop_table('crm_settings')
