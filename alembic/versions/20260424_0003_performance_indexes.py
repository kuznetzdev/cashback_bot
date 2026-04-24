"""performance indexes for ranking bulk query

Revision ID: 20260424_0003
Revises: 20260311_0002

Adds a covering index on ``cashback_items(bank_id, normalized_category)`` so
the bulk ranking query (single JOIN over banks + cashback_items for a given
user) is served entirely from the index without touching the heap for the
category slug. Also adds a composite index on ``user_logs(user_id, action,
created_at)`` since the reminder use case filters by exactly those columns.

idx_user_identity_provider is intentionally skipped — the existing UNIQUE
constraint ``uq_user_identities_provider_identity(provider, provider_user_id)``
already provides an equivalent covering index.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260424_0003"
down_revision = "20260311_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Covering index for the JOIN used by RankingSnapshot / best-card lookups.
    op.create_index(
        "ix_cashback_items_bank_category",
        "cashback_items",
        ["bank_id", "normalized_category"],
        unique=False,
    )
    # Accelerates SendMonthlyReminders' "already sent this month?" check which
    # filters by (user_id, action, created_at).
    op.create_index(
        "ix_user_logs_user_action_created",
        "user_logs",
        ["user_id", "action", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_user_logs_user_action_created", table_name="user_logs")
    op.drop_index("ix_cashback_items_bank_category", table_name="cashback_items")
