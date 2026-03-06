from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import SourceType
from app.db.base import Base, TimestampMixin

JSON_VARIANT = JSON().with_variant(JSONB, "postgresql")
PK_TYPE = BigInteger().with_variant(Integer, "sqlite")


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="ru")
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    banks: Mapped[list["Bank"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    logs: Mapped[list["UserLog"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Bank(TimestampMixin, Base):
    __tablename__ = "banks"
    __table_args__ = (
        UniqueConstraint("user_id", "bank_name", name="uq_banks_user_bank_name"),
        Index("ix_banks_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    bank_name: Mapped[str] = mapped_column(Text, nullable=False)

    user: Mapped[User] = relationship(back_populates="banks")
    cashback_items: Mapped[list["CashbackItem"]] = relationship(
        back_populates="bank",
        cascade="all, delete-orphan",
    )


class CashbackItem(TimestampMixin, Base):
    __tablename__ = "cashback_items"
    __table_args__ = (
        Index("ix_cashback_items_bank_id", "bank_id"),
        Index("ix_cashback_items_normalized_category", "normalized_category"),
    )

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    bank_id: Mapped[int] = mapped_column(ForeignKey("banks.id", ondelete="CASCADE"), nullable=False)
    raw_category: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_category: Mapped[str] = mapped_column(Text, nullable=False)
    percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False, default=SourceType.MANUAL.value)

    bank: Mapped[Bank] = relationship(back_populates="cashback_items")


class UserLog(Base):
    __tablename__ = "user_logs"
    __table_args__ = (Index("ix_user_logs_user_id_created_at", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON_VARIANT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False)

    user: Mapped[User] = relationship(back_populates="logs")
