"""lead intake

Fase 2D: who gets new leads per motor (crm_assignments), lead submissions for
rate limiting, and opportunities.origin_ref for idempotent imports.
Seeds sector_publico and the fallback (_default) with the admin Gerardo
(decision of 27/09/2026); the other motors are set from Clientes → Asignación.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-27 11:25:44.440664

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('lead_submissions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('ip_address', sa.String(length=50), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_lead_submissions_created_at'), 'lead_submissions', ['created_at'], unique=False)
    op.create_table('crm_assignments',
    sa.Column('motor', sa.String(length=30), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('motor')
    )
    op.add_column('opportunities', sa.Column('origin_ref', sa.String(length=80), nullable=True))
    op.create_index(op.f('ix_opportunities_origin_ref'), 'opportunities', ['origin_ref'], unique=False)

    op.execute(
        "INSERT INTO crm_assignments (motor, user_id) "
        "SELECT m.motor, (SELECT id FROM users WHERE role = 'admin' AND full_name ILIKE 'gerardo%' ORDER BY id LIMIT 1) "
        "FROM (VALUES ('sector_publico'), ('_default')) AS m(motor)"
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_opportunities_origin_ref'), table_name='opportunities')
    op.drop_column('opportunities', 'origin_ref')
    op.drop_table('crm_assignments')
    op.drop_index(op.f('ix_lead_submissions_created_at'), table_name='lead_submissions')
    op.drop_table('lead_submissions')
