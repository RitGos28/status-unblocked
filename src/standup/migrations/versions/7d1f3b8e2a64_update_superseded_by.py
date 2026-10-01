"""update superseded_by for one-update-per-member-per-cycle

Revision ID: 7d1f3b8e2a64
Revises: 4c2e9a7d1b3f
Create Date: 2026-10-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7d1f3b8e2a64'
down_revision: Union[str, None] = '4c2e9a7d1b3f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('update') as batch_op:
        batch_op.add_column(sa.Column('superseded_by', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            'fk_update_superseded_by_update', 'update', ['superseded_by'], ['id']
        )


def downgrade() -> None:
    with op.batch_alter_table('update') as batch_op:
        batch_op.drop_constraint('fk_update_superseded_by_update', type_='foreignkey')
        batch_op.drop_column('superseded_by')
