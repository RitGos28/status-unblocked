"""member teams_conversation_ref for proactive digest notices

Revision ID: c8d2e4f6a713
Revises: b3c7d9e1f205
Create Date: 2026-10-01 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8d2e4f6a713'
down_revision: Union[str, None] = 'b3c7d9e1f205'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('member') as batch_op:
        batch_op.add_column(sa.Column('teams_conversation_ref', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('member') as batch_op:
        batch_op.drop_column('teams_conversation_ref')
