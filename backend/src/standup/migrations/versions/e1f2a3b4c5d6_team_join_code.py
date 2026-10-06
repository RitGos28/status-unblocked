"""team.join_code: the code a team's members type to sign in

Revision ID: e1f2a3b4c5d6
Revises: d0e2f4a6b8c1
Create Date: 2026-10-07 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from standup.auth.team_code import generate_team_code


# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, None] = 'd0e2f4a6b8c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('team', sa.Column('join_code', sa.String(length=16), nullable=True))
    bind = op.get_bind()
    for team_id, slug in bind.execute(sa.text('SELECT id, slug FROM team')).fetchall():
        bind.execute(
            sa.text('UPDATE team SET join_code = :code WHERE id = :id'),
            {'code': generate_team_code(slug), 'id': team_id},
        )
    with op.batch_alter_table('team') as batch:
        batch.alter_column('join_code', existing_type=sa.String(length=16), nullable=False)
        batch.create_unique_constraint('uq_team_join_code', ['join_code'])


def downgrade() -> None:
    with op.batch_alter_table('team') as batch:
        batch.drop_constraint('uq_team_join_code', type_='unique')
        batch.drop_column('join_code')
