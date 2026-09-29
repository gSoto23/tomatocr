"""why an account was discarded

Discarding (from the account or from one of its opportunities) asks for a reason; the
"Descartados" list shows it.

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-29 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0012'
down_revision: Union[str, None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('accounts', sa.Column('discard_reason', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('accounts', 'discard_reason')
