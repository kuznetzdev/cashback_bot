"""platform identity foundation

Revision ID: 20260311_0002
Revises: 20260306_0001
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260311_0002"
down_revision = "20260306_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("display_name", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE users
        SET display_name = COALESCE(
            NULLIF(full_name, ''),
            NULLIF(username, ''),
            'telegram:' || CAST(telegram_user_id AS TEXT),
            'user:' || CAST(id AS TEXT)
        )
        """
    )
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("display_name", existing_type=sa.Text(), nullable=False)
        batch_op.alter_column("telegram_user_id", existing_type=sa.BigInteger(), nullable=True)

    op.create_table(
        "user_identities",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_user_id", sa.Text(), nullable=False),
        sa.Column("provider_username", sa.Text(), nullable=True),
        sa.Column("provider_display_name", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "provider_user_id", name="uq_user_identities_provider_identity"),
        sa.UniqueConstraint("user_id", "provider", name="uq_user_identities_user_provider"),
    )
    op.create_index("ix_user_identities_user_id", "user_identities", ["user_id"])
    op.execute(
        """
        INSERT INTO user_identities (
            user_id,
            provider,
            provider_user_id,
            provider_username,
            provider_display_name
        )
        SELECT
            u.id,
            'telegram',
            CAST(u.telegram_user_id AS TEXT),
            u.username,
            u.full_name
        FROM users u
        WHERE u.telegram_user_id IS NOT NULL
          AND u.id = (
              SELECT MIN(u2.id)
              FROM users u2
              WHERE u2.telegram_user_id = u.telegram_user_id
          )
        """
    )

    op.create_table(
        "local_credentials",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", name="uq_local_credentials_user_id"),
        sa.UniqueConstraint("username", name="uq_local_credentials_username"),
        sa.UniqueConstraint("email", name="uq_local_credentials_email"),
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE users
        SET
            telegram_user_id = (
                SELECT CAST(ui.provider_user_id AS BIGINT)
                FROM user_identities ui
                WHERE ui.user_id = users.id AND ui.provider = 'telegram'
                LIMIT 1
            ),
            username = (
                SELECT ui.provider_username
                FROM user_identities ui
                WHERE ui.user_id = users.id AND ui.provider = 'telegram'
                LIMIT 1
            ),
            full_name = (
                SELECT ui.provider_display_name
                FROM user_identities ui
                WHERE ui.user_id = users.id AND ui.provider = 'telegram'
                LIMIT 1
            )
        """
    )
    op.drop_table("local_credentials")
    op.drop_index("ix_user_identities_user_id", table_name="user_identities")
    op.drop_table("user_identities")
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("telegram_user_id", existing_type=sa.BigInteger(), nullable=False)
        batch_op.drop_column("display_name")
