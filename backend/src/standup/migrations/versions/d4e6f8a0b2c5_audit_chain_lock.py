"""audit_chain_head lock row and UNIQUE(audit_log.prev_hash)

Revision ID: d4e6f8a0b2c5
Revises: c8d2e4f6a713
Create Date: 2026-10-01 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e6f8a0b2c5'
down_revision: Union[str, None] = 'c8d2e4f6a713'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    forks = bind.execute(
        sa.text(
            "SELECT prev_hash, COUNT(*) FROM audit_log "
            "GROUP BY prev_hash HAVING COUNT(*) > 1"
        )
    ).all()
    if forks:
        raise RuntimeError(
            f"audit_log is already forked: {len(forks)} prev_hash value(s) are shared by "
            "more than one row, so UNIQUE(prev_hash) cannot be added. This chain was "
            "damaged by the concurrency bug this migration fixes; it cannot be repaired "
            "without rewriting history. Export what you need, then start a new chain."
        )

    op.create_table(
        'audit_chain_head',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    count = bind.execute(sa.text("SELECT COUNT(*) FROM audit_log")).scalar() or 0
    bind.execute(sa.text("INSERT INTO audit_chain_head (id, seq) VALUES (1, :n)"), {"n": count})

    with op.batch_alter_table('audit_log') as batch_op:
        batch_op.create_unique_constraint('uq_audit_log_prev_hash', ['prev_hash'])


def downgrade() -> None:
    with op.batch_alter_table('audit_log') as batch_op:
        batch_op.drop_constraint('uq_audit_log_prev_hash', type_='unique')
    op.drop_table('audit_chain_head')
