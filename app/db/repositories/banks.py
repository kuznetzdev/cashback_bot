from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Bank


class BanksRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_user(self, user_id: int) -> list[Bank]:
        result = await self.session.execute(
            select(Bank)
            .where(Bank.user_id == user_id)
            .order_by(func.lower(Bank.bank_name))
        )
        return list(result.scalars().all())

    async def get_for_user(self, user_id: int, bank_id: int) -> Bank | None:
        result = await self.session.execute(
            select(Bank).where(Bank.user_id == user_id, Bank.id == bank_id)
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, user_id: int, bank_name: str) -> Bank | None:
        result = await self.session.execute(
            select(Bank).where(
                Bank.user_id == user_id,
                func.lower(Bank.bank_name) == bank_name.strip().lower(),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, user_id: int, bank_name: str) -> Bank:
        bank = Bank(user_id=user_id, bank_name=bank_name.strip())
        self.session.add(bank)
        await self.session.flush()
        return bank

    async def delete(self, bank: Bank) -> None:
        await self.session.delete(bank)
