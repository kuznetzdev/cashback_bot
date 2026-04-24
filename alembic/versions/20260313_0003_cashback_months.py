"""cashback snapshots by month

Revision ID: 20260313_0003
Revises: 20260311_0002
"""

from __future__ import annotations

from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision = "20260313_0003"
down_revision = "20260311_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cashback_items", sa.Column("target_month", sa.String(length=7), nullable=True))
    current_month = datetime.now().strftime("%Y-%m")
    op.execute(sa.text("UPDATE cashback_items SET target_month = :target_month WHERE target_month IS NULL").bindparams(target_month=current_month))
    with op.batch_alter_table("cashback_items") as batch_op:
        batch_op.alter_column("target_month", existing_type=sa.String(length=7), nullable=False)
    op.create_index("ix_cashback_items_bank_id_target_month", "cashback_items", ["bank_id", "target_month"])


def downgrade() -> None:
    op.drop_index("ix_cashback_items_bank_id_target_month", table_name="cashback_items")
    with op.batch_alter_table("cashback_items") as batch_op:
        batch_op.drop_column("target_month")
