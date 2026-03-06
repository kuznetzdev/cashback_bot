from __future__ import annotations

from decimal import Decimal

from rapidfuzz import process
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DEFAULT_HISTORY_LIMIT
from app.core.enums import SourceType
from app.core.exceptions import NotFoundError, ValidationError
from app.db.models import User
from app.db.repositories.banks import BanksRepository
from app.db.repositories.cashback_items import CashbackItemsRepository
from app.db.repositories.logs import LogsRepository
from app.schemas.bank import BankDetails, BankRead
from app.schemas.cashback_item import CashbackItemRead, DraftCashbackItem, RankingEntry
from app.services.categories import CategoryService
from app.services.history import HistoryService


class CatalogService:
    def __init__(self, category_service: CategoryService) -> None:
        self.category_service = category_service

    async def list_banks(self, session: AsyncSession, user: User) -> list[BankRead]:
        banks = await BanksRepository(session).list_for_user(user.id)
        return [BankRead(id=bank.id, bank_name=bank.bank_name) for bank in banks]

    async def get_bank_details(self, session: AsyncSession, user: User, bank_id: int) -> BankDetails:
        bank = await BanksRepository(session).get_for_user(user.id, bank_id)
        if bank is None:
            raise NotFoundError("errors.bank_not_found")

        items = await CashbackItemsRepository(session).list_for_bank(bank.id)
        return BankDetails(
            id=bank.id,
            bank_name=bank.bank_name,
            items=[
                CashbackItemRead(
                    id=item.id,
                    raw_category=item.raw_category,
                    normalized_category=item.normalized_category,
                    percent=item.percent,
                    source_type=item.source_type,
                    display_category=self.category_service.display_name(item.normalized_category, user.language),
                )
                for item in items
            ],
        )

    async def save_bank(
        self,
        session: AsyncSession,
        user: User,
        *,
        bank_name: str,
        items: list[DraftCashbackItem],
        source_type: str,
        bank_id: int | None = None,
    ) -> BankRead:
        cleaned_name = bank_name.strip()
        if not cleaned_name:
            raise ValidationError("errors.invalid_bank_name")
        if not items:
            raise ValidationError("errors.no_items_to_save")
        if any(item.percent <= 0 for item in items):
            raise ValidationError("errors.zero_percent_not_allowed")

        banks_repo = BanksRepository(session)
        bank = await banks_repo.get_for_user(user.id, bank_id) if bank_id else None
        created = False
        if bank is None:
            bank = await banks_repo.get_by_name(user.id, cleaned_name)
        if bank is None:
            bank = await banks_repo.create(user.id, cleaned_name)
            created = True
        else:
            bank.bank_name = cleaned_name
            await session.flush()

        normalized_items = [
            item.model_copy(update={"source_type": source_type or item.source_type or SourceType.MANUAL.value})
            for item in items
        ]
        await CashbackItemsRepository(session).replace_for_bank(bank.id, normalized_items)
        await HistoryService(session).log(
            user.id,
            "bank_added" if created else "bank_updated",
            {
                "bank_id": bank.id,
                "bank_name": bank.bank_name,
                "items_count": len(normalized_items),
            },
        )
        return BankRead(id=bank.id, bank_name=bank.bank_name)

    async def delete_bank(self, session: AsyncSession, user: User, bank_id: int) -> None:
        banks_repo = BanksRepository(session)
        bank = await banks_repo.get_for_user(user.id, bank_id)
        if bank is None:
            raise NotFoundError("errors.bank_not_found")
        await HistoryService(session).log(user.id, "bank_deleted", {"bank_id": bank.id, "bank_name": bank.bank_name})
        await banks_repo.delete(bank)

    async def delete_bank_by_name(self, session: AsyncSession, user: User, bank_name: str) -> BankRead:
        banks = await BanksRepository(session).list_for_user(user.id)
        if not banks:
            raise NotFoundError("errors.bank_not_found")
        names = [bank.bank_name for bank in banks]
        match = process.extractOne(bank_name, names, score_cutoff=70)
        if not match:
            raise NotFoundError("errors.bank_not_found")
        bank = next(item for item in banks if item.bank_name == match[0])
        await self.delete_bank(session, user, bank.id)
        return BankRead(id=bank.id, bank_name=bank.bank_name)

    async def delete_category_by_query(self, session: AsyncSession, user: User, category_query: str) -> tuple[int, int]:
        banks = await BanksRepository(session).list_for_user(user.id)
        items_repo = CashbackItemsRepository(session)
        matched_slugs = self.category_service.expand_query_slugs(category_query)

        total_deleted = 0
        touched_banks = 0
        for bank in banks:
            items = await items_repo.list_for_bank(bank.id)
            remaining = [
                DraftCashbackItem(
                    raw_category=item.raw_category,
                    normalized_category=item.normalized_category,
                    percent=item.percent,
                    source_type=item.source_type,
                )
                for item in items
                if item.normalized_category not in matched_slugs
            ]
            deleted_here = len(items) - len(remaining)
            if deleted_here <= 0:
                continue
            total_deleted += deleted_here
            touched_banks += 1
            await items_repo.replace_for_bank(bank.id, remaining)

        if total_deleted == 0:
            raise NotFoundError("errors.category_not_found")

        await HistoryService(session).log(
            user.id,
            "category_deleted",
            {
                "query": category_query,
                "deleted_items": total_deleted,
                "affected_banks": touched_banks,
            },
        )
        return total_deleted, touched_banks

    async def list_ranking_entries(self, session: AsyncSession, user: User) -> list[RankingEntry]:
        entries: list[RankingEntry] = []
        banks = await BanksRepository(session).list_for_user(user.id)
        items_repo = CashbackItemsRepository(session)
        for bank in banks:
            items = await items_repo.list_for_bank(bank.id)
            for item in items:
                entries.append(
                    RankingEntry(
                        bank_id=bank.id,
                        bank_name=bank.bank_name,
                        normalized_category=item.normalized_category,
                        percent=Decimal(item.percent),
                    )
                )
        return entries

    async def list_history(self, session: AsyncSession, user: User, limit: int = DEFAULT_HISTORY_LIMIT) -> list:
        return await LogsRepository(session).list_recent(user.id, limit)

    async def update_language(self, session: AsyncSession, user: User, language: str) -> None:
        user.language = language
        await session.flush()
        await HistoryService(session).log(user.id, "language_changed", {"language": language})

    async def toggle_notifications(self, session: AsyncSession, user: User) -> bool:
        user.notifications_enabled = not user.notifications_enabled
        await session.flush()
        await HistoryService(session).log(
            user.id,
            "notifications_toggled",
            {"notifications_enabled": user.notifications_enabled},
        )
        return user.notifications_enabled
