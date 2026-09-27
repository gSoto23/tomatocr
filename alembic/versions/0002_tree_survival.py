"""tree survival

Fase 1: tree status and monitoring checks, project kind (institucional /
darboles), public-name authorization and link to an operations project.

The only project in production at this point is the Municipalidad de
Alajuela public contract; its name was authorized for the public map
(decision of 27/09/2026), so it keeps showing as before.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-26 23:27:24.849200

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('tree_checks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tree_id', sa.Integer(), nullable=False),
    sa.Column('checked_at', sa.Date(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('height_cm', sa.Float(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('photo_path', sa.String(length=500), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('daily_log_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['daily_log_id'], ['daily_logs.id'], ),
    sa.ForeignKeyConstraint(['tree_id'], ['reforestation_trees.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tree_checks_id'), 'tree_checks', ['id'], unique=False)
    op.create_index(op.f('ix_tree_checks_tree_id'), 'tree_checks', ['tree_id'], unique=False)
    op.add_column('reforestation_projects', sa.Column('project_id', sa.Integer(), nullable=True))
    op.add_column('reforestation_projects', sa.Column('kind', sa.String(length=20), server_default='institucional', nullable=False))
    op.add_column('reforestation_projects', sa.Column('is_public', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('reforestation_projects', sa.Column('public_name', sa.String(length=255), nullable=True))
    op.add_column('reforestation_projects', sa.Column('consent_date', sa.Date(), nullable=True))
    op.create_foreign_key('fk_reforestation_projects_project_id', 'reforestation_projects', 'projects', ['project_id'], ['id'])
    op.add_column('reforestation_trees', sa.Column('status', sa.String(length=20), server_default='sin_verificar', nullable=False))
    op.add_column('reforestation_trees', sa.Column('last_checked_at', sa.Date(), nullable=True))
    op.add_column('reforestation_trees', sa.Column('replaced_by_id', sa.Integer(), nullable=True))
    op.create_unique_constraint('uq_reforestation_trees_project_number', 'reforestation_trees', ['project_id', 'tree_number'])
    op.create_foreign_key('fk_reforestation_trees_replaced_by_id', 'reforestation_trees', 'reforestation_trees', ['replaced_by_id'], ['id'])

    op.execute(
        "UPDATE reforestation_projects SET is_public = true, public_name = 'Municipalidad de Alajuela' "
        "WHERE client_name = 'Municipalidad Alajuela'"
    )


def downgrade() -> None:
    op.drop_constraint('fk_reforestation_trees_replaced_by_id', 'reforestation_trees', type_='foreignkey')
    op.drop_constraint('uq_reforestation_trees_project_number', 'reforestation_trees', type_='unique')
    op.drop_column('reforestation_trees', 'replaced_by_id')
    op.drop_column('reforestation_trees', 'last_checked_at')
    op.drop_column('reforestation_trees', 'status')
    op.drop_constraint('fk_reforestation_projects_project_id', 'reforestation_projects', type_='foreignkey')
    op.drop_column('reforestation_projects', 'consent_date')
    op.drop_column('reforestation_projects', 'public_name')
    op.drop_column('reforestation_projects', 'is_public')
    op.drop_column('reforestation_projects', 'kind')
    op.drop_column('reforestation_projects', 'project_id')
    op.drop_index(op.f('ix_tree_checks_tree_id'), table_name='tree_checks')
    op.drop_index(op.f('ix_tree_checks_id'), table_name='tree_checks')
    op.drop_table('tree_checks')
