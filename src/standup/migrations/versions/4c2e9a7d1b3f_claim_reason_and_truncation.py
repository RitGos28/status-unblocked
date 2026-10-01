"""persist claim matched_rule and digest truncated_count

Revision ID: 4c2e9a7d1b3f
Revises: 1b78bf89715f
Create Date: 2026-10-01 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4c2e9a7d1b3f'
down_revision: Union[str, None] = '1b78bf89715f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('digest_claim') as batch_op:
        batch_op.add_column(
            sa.Column('matched_rule', sa.String(length=120), nullable=False, server_default='')
        )
    with op.batch_alter_table('digest') as batch_op:
        batch_op.add_column(
            sa.Column('truncated_count', sa.Integer(), nullable=False, server_default='0')
        )


def downgrade() -> None:
    with op.batch_alter_table('digest') as batch_op:
        batch_op.drop_column('truncated_count')
    with op.batch_alter_table('digest_claim') as batch_op:
        batch_op.drop_column('matched_rule')
