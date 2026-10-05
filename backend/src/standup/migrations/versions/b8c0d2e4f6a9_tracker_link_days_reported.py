"""tracker_link days_reported, the running count in structured issue updates

Revision ID: b8c0d2e4f6a9
Revises: a7b9c1d3e5f8
Create Date: 2026-10-05 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8c0d2e4f6a9'
down_revision: Union[str, None] = 'a7b9c1d3e5f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('tracker_link') as batch_op:
        batch_op.add_column(
            sa.Column('days_reported', sa.Integer(), nullable=False, server_default='1')
        )


def downgrade() -> None:
    with op.batch_alter_table('tracker_link') as batch_op:
        batch_op.drop_column('days_reported')
