"""cashback_items: add monthly_limit nullable column

Revision ID: 20260425_0004
Revises: 20260424_0003

Adds the optional ``monthly_limit`` column to ``cashback_items``. Many
real Russian-bank offers come with a per-month cap ("АЗС 5% до 3000 ₽"),
so the parser captures the number when present and the ranker uses it
to choose the card with the best *effective* cashback for a given spend.

The column is nullable because the data we have until this migration
ran has no limit information; we don't want to invent a value.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260425_0004"
down_revision = "20260424_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cashback_items",
        sa.Column("monthly_limit", sa.Numeric(12, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cashback_items", "monthly_limit")
