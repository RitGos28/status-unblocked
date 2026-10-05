"""standup_cycle notified_at: one digest notice per cycle

Revision ID: a7b9c1d3e5f8
Revises: f6a8b0c2d4e7
Create Date: 2026-10-01 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7b9c1d3e5f8'
down_revision: Union[str, None] = 'f6a8b0c2d4e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('standup_cycle') as batch_op:
        batch_op.add_column(sa.Column('notified_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('standup_cycle') as batch_op:
        batch_op.drop_column('notified_at')
