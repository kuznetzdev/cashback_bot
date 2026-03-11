from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0)


class Base(DeclarativeBase):
    pass


JSON_VARIANT = JSON().with_variant(JSONB, "postgresql")
BIGINT_PK = BigInteger().with_variant(Integer, "sqlite")


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    username: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="ru")
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow, onupdate=utcnow)


class UserIdentityModel(Base):
    __tablename__ = "user_identities"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_user_identities_provider_identity"),
        UniqueConstraint("user_id", "provider", name="uq_user_identities_user_provider"),
        Index("ix_user_identities_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    provider_username: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow, onupdate=utcnow)


class LocalCredentialsModel(Base):
    __tablename__ = "local_credentials"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_local_credentials_user_id"),
        UniqueConstraint("username", name="uq_local_credentials_username"),
        UniqueConstraint("email", name="uq_local_credentials_email"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow, onupdate=utcnow)


class BankModel(Base):
    __tablename__ = "banks"
    __table_args__ = (
        UniqueConstraint("user_id", "bank_name", name="uq_banks_user_bank_name"),
        Index("ix_banks_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    bank_name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow, onupdate=utcnow)


class CashbackItemModel(Base):
    __tablename__ = "cashback_items"
    __table_args__ = (
        Index("ix_cashback_items_bank_id", "bank_id"),
        Index("ix_cashback_items_normalized_category", "normalized_category"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    bank_id: Mapped[int] = mapped_column(ForeignKey("banks.id", ondelete="CASCADE"), nullable=False)
    raw_category: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_category: Mapped[str] = mapped_column(Text, nullable=False)
    percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow, onupdate=utcnow)


class UserLogModel(Base):
    __tablename__ = "user_logs"
    __table_args__ = (Index("ix_user_logs_user_id_created_at", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[dict | None] = mapped_column(JSON_VARIANT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)
