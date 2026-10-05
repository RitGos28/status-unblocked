"""member teams_aad_id and the content-free ingest_rejection table

Revision ID: 9e4a2c6f8b10
Revises: 7d1f3b8e2a64
Create Date: 2026-10-01 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9e4a2c6f8b10'
down_revision: Union[str, None] = '7d1f3b8e2a64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ingest_rejection',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('source', sa.String(length=16), nullable=False),
        sa.Column('reason', sa.String(length=64), nullable=False),
        sa.Column('conversation_type', sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('member') as batch_op:
        batch_op.add_column(sa.Column('teams_aad_id', sa.String(length=64), nullable=True))
        batch_op.create_index('ix_member_teams_aad_id', ['teams_aad_id'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('member') as batch_op:
        batch_op.drop_index('ix_member_teams_aad_id')
        batch_op.drop_column('teams_aad_id')
    op.drop_table('ingest_rejection')
