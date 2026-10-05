"""digest build_seq and inputs_sha256; standup_cycle build_seq: one build at a time

Revision ID: d0e2f4a6b8c1
Revises: c9d1e3f5a7b0
Create Date: 2026-10-05 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd0e2f4a6b8c1'
down_revision: Union[str, None] = 'c9d1e3f5a7b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('standup_cycle') as batch_op:
        batch_op.add_column(
            sa.Column('build_seq', sa.Integer(), nullable=False, server_default='0')
        )
    with op.batch_alter_table('digest') as batch_op:
        batch_op.add_column(
            sa.Column('build_seq', sa.Integer(), nullable=False, server_default='0')
        )
        batch_op.add_column(
            sa.Column('inputs_sha256', sa.String(64), nullable=False, server_default='')
        )
    # Number existing digests in the order they were built, per day.
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, cycle_id FROM digest ORDER BY cycle_id, generated_at, id")
    ).all()
    counters: dict[str, int] = {}
    for digest_id, cycle_id in rows:
        counters[cycle_id] = counters.get(cycle_id, 0) + 1
        bind.execute(
            sa.text("UPDATE digest SET build_seq = :seq WHERE id = :id"),
            {"seq": counters[cycle_id], "id": digest_id},
        )
    for cycle_id, seq in counters.items():
        bind.execute(
            sa.text("UPDATE standup_cycle SET build_seq = :seq WHERE id = :id"),
            {"seq": seq, "id": cycle_id},
        )


def downgrade() -> None:
    with op.batch_alter_table('digest') as batch_op:
        batch_op.drop_column('inputs_sha256')
        batch_op.drop_column('build_seq')
    with op.batch_alter_table('standup_cycle') as batch_op:
        batch_op.drop_column('build_seq')
