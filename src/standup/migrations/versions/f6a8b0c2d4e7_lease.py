"""lease table for single-runner work (outbox drain, scheduler)

Revision ID: f6a8b0c2d4e7
Revises: e5f7a9b1c3d6
Create Date: 2026-10-01 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6a8b0c2d4e7'
down_revision: Union[str, None] = 'e5f7a9b1c3d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'lease',
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('holder', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('name'),
    )


def downgrade() -> None:
    op.drop_table('lease')
