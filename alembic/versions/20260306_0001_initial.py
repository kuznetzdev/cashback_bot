"""initial schema"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260306_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("username", sa.Text(), nullable=True),
        sa.Column("full_name", sa.Text(), nullable=True),
        sa.Column("language", sa.String(length=8), nullable=False, server_default="ru"),
        sa.Column("notifications_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now())
    )

    op.create_table(
        "banks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bank_name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "bank_name", name="uq_banks_user_bank_name"),
    )
    op.create_index("ix_banks_user_id", "banks", ["user_id"])

    op.create_table(
        "cashback_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("bank_id", sa.BigInteger(), sa.ForeignKey("banks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("raw_category", sa.Text(), nullable=False),
        sa.Column("normalized_category", sa.Text(), nullable=False),
        sa.Column("percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now())
    )
    op.create_index("ix_cashback_items_bank_id", "cashback_items", ["bank_id"])
    op.create_index("ix_cashback_items_normalized_category", "cashback_items", ["normalized_category"])

    op.create_table(
        "user_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now())
    )
    op.create_index("ix_user_logs_user_id_created_at", "user_logs", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_user_logs_user_id_created_at", table_name="user_logs")
    op.drop_table("user_logs")
    op.drop_index("ix_cashback_items_normalized_category", table_name="cashback_items")
    op.drop_index("ix_cashback_items_bank_id", table_name="cashback_items")
    op.drop_table("cashback_items")
    op.drop_index("ix_banks_user_id", table_name="banks")
    op.drop_table("banks")
    op.drop_table("users")
