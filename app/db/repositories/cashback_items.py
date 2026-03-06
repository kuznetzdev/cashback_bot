from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CashbackItem
from app.schemas.cashback_item import DraftCashbackItem


class CashbackItemsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_bank(self, bank_id: int) -> list[CashbackItem]:
        result = await self.session.execute(
            select(CashbackItem)
            .where(CashbackItem.bank_id == bank_id)
            .order_by(CashbackItem.percent.desc(), CashbackItem.normalized_category.asc())
        )
        return list(result.scalars().all())

    async def replace_for_bank(self, bank_id: int, items: list[DraftCashbackItem]) -> None:
        await self.session.execute(delete(CashbackItem).where(CashbackItem.bank_id == bank_id))
        for item in items:
            self.session.add(
                CashbackItem(
                    bank_id=bank_id,
                    raw_category=item.raw_category,
                    normalized_category=item.normalized_category,
                    percent=item.percent,
                    source_type=item.source_type,
                )
            )
        await self.session.flush()
