"""update_item.text nullable: retention removes lines no digest quoted

Revision ID: c9d1e3f5a7b0
Revises: b8c0d2e4f6a9
Create Date: 2026-10-05 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9d1e3f5a7b0'
down_revision: Union[str, None] = 'b8c0d2e4f6a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('update_item') as batch_op:
        batch_op.alter_column('text', existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    op.execute("UPDATE update_item SET text = '' WHERE text IS NULL")
    with op.batch_alter_table('update_item') as batch_op:
        batch_op.alter_column('text', existing_type=sa.Text(), nullable=False)
