"""tracker_link, tracker_outbox, and digest_claim.tracker_fingerprint

Revision ID: b3c7d9e1f205
Revises: 9e4a2c6f8b10
Create Date: 2026-10-01 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3c7d9e1f205'
down_revision: Union[str, None] = '9e4a2c6f8b10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tracker_link',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('fingerprint', sa.String(length=64), nullable=False),
        sa.Column('team_id', sa.String(length=36), nullable=False),
        sa.Column('member_id', sa.String(length=36), nullable=False),
        sa.Column('provider', sa.String(length=16), nullable=False),
        sa.Column('repo', sa.String(length=200), nullable=False),
        sa.Column('issue_number', sa.Integer(), nullable=False),
        sa.Column('issue_url', sa.String(length=500), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_cycle_id', sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(['member_id'], ['member.id']),
        sa.ForeignKeyConstraint(['team_id'], ['team.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('fingerprint'),
    )
    op.create_table(
        'tracker_outbox',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('fingerprint', sa.String(length=64), nullable=False),
        sa.Column('team_id', sa.String(length=36), nullable=False),
        sa.Column('member_id', sa.String(length=36), nullable=False),
        sa.Column('cycle_id', sa.String(length=36), nullable=False),
        sa.Column('digest_id', sa.String(length=36), nullable=False),
        sa.Column('payload_json', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_error', sa.String(length=300), nullable=False),
        sa.ForeignKeyConstraint(['cycle_id'], ['standup_cycle.id']),
        sa.ForeignKeyConstraint(['digest_id'], ['digest.id']),
        sa.ForeignKeyConstraint(['member_id'], ['member.id']),
        sa.ForeignKeyConstraint(['team_id'], ['team.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('fingerprint', 'cycle_id', name='uq_outbox_fingerprint_cycle'),
    )
    with op.batch_alter_table('digest_claim') as batch_op:
        batch_op.add_column(
            sa.Column('tracker_fingerprint', sa.String(length=64), nullable=False, server_default='')
        )


def downgrade() -> None:
    with op.batch_alter_table('digest_claim') as batch_op:
        batch_op.drop_column('tracker_fingerprint')
    op.drop_table('tracker_outbox')
    op.drop_table('tracker_link')
