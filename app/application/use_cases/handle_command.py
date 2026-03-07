from __future__ import annotations

import logging
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from pathlib import Path

from rapidfuzz import process

from app.application.contracts.ports import OCRPort, UnitOfWorkPort
from app.application.models import Action, Effect, Screen, UserCommand, WorkflowResult, WorkflowState
from app.domain.enums import SourceType
from app.domain.errors import NotFoundError, ValidationError
from app.domain.models import BankAggregate, CashbackDraftItem, UserProfile
from app.domain.services.categories import CategoryService
from app.domain.services.parsing import ParserService
from app.domain.services.ranking import RankingEntry, RankingService

POPULAR_BANKS = [
    "T-Bank",
    "Sber",
    "Alfa",
    "VTB",
    "Gazprombank",
    "Raiffeisen",
    "Ozon",
    "Yandex Pay",
]

logger = logging.getLogger(__name__)


class HandleCommandUseCase:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWorkPort],
        parser: ParserService,
        categories: CategoryService,
        ranking: RankingService,
        ocr: OCRPort,
    ) -> None:
        self.uow_factory = uow_factory
        self.parser = parser
        self.categories = categories
        self.ranking = ranking
        self.ocr = ocr

    async def execute(self, user: UserProfile, state: WorkflowState, command: UserCommand) -> WorkflowResult:
        name = command.name
        if name == "continue_draft":
            self._clear_interrupt_target(state)
            return WorkflowResult(user=user, state=state, screen=self._preview_screen(state, user.language))
        if name == "discard_draft_and_go":
            target_command = self._take_interrupt_target(state)
            await self._log_user_action(user.id, "draft_discarded_via_interrupt", {"target": target_command.name})
            result = await self.execute(user, WorkflowState(), target_command)
            result.effects.append(Effect(kind="show_status", payload={"message_key": "messages.draft_discarded", "transient": True}))
            return result
        if name == "save_draft_and_go":
            if not self._can_save_draft(state):
                raise ValidationError("errors.no_items_to_save")
            target_command = self._take_interrupt_target(state)
            await self._save_bank(user.id, state)
            await self._log_user_action(user.id, "draft_saved_via_interrupt", {"target": target_command.name})
            result = await self.execute(user, WorkflowState(), target_command)
            result.effects.append(Effect(kind="show_status", payload={"message_key": "messages.saved_bank", "transient": True}))
            return result

        if self._should_interrupt_navigation(state, command):
            self._set_interrupt_target(state, command)
            await self._log_user_action(user.id, "draft_interrupt_prompt", {"target": command.name})
            return WorkflowResult(user=user, state=state, screen=self._interrupt_screen(state))

        if name in {"start", "open_home"}:
            return WorkflowResult(user=user, state=WorkflowState(), screen=self._home_screen())
        if name == "open_help":
            return WorkflowResult(user=user, state=state, screen=self._help_screen())
        if name == "open_add_bank":
            return WorkflowResult(user=user, state=WorkflowState(mode="create"), screen=self._choose_bank_screen())
        if name == "select_bank_preset":
            index = int(command.payload["index"])
            if index < 0 or index >= len(POPULAR_BANKS):
                raise ValidationError("errors.invalid_bank_name")
            state.selected_bank_name = POPULAR_BANKS[index]
            state.selected_bank_id = None
            state.pending_input_kind = None
            state.temp_payload = {}
            return WorkflowResult(user=user, state=state, screen=self._input_method_screen(state.selected_bank_name))
        if name == "select_bank_other":
            state.pending_input_kind = "custom_bank_name"
            return WorkflowResult(user=user, state=state, screen=self._custom_bank_prompt_screen())
        if name == "submit_custom_bank_name":
            bank_name = str(command.payload["text"]).strip()
            if not bank_name:
                raise ValidationError("errors.invalid_bank_name")
            state.selected_bank_name = bank_name
            state.selected_bank_id = None
            state.pending_input_kind = None
            return WorkflowResult(user=user, state=state, screen=self._input_method_screen(bank_name))
        if name == "choose_input_method":
            method = str(command.payload["method"])
            if method == "manual":
                state.pending_input_kind = "manual_lines"
                state.temp_payload["source_type"] = SourceType.MANUAL.value
                await self._log_user_action(user.id, "input_method_selected", {"method": "manual"})
                return WorkflowResult(user=user, state=state, screen=self._manual_prompt_screen())
            if method == "photo":
                state.pending_input_kind = "photo_upload"
                state.temp_payload["source_type"] = SourceType.OCR.value
                await self._log_user_action(user.id, "input_method_selected", {"method": "photo"})
                return WorkflowResult(user=user, state=state, screen=self._photo_prompt_screen())
            if method == "template":
                state.pending_input_kind = None
                state.temp_payload["source_type"] = SourceType.TEMPLATE.value
                state.draft_items = [
                    CashbackDraftItem(
                        raw_category=self.categories.display_name(slug, user.language),
                        normalized_category=slug,
                        percent=Decimal("0"),
                        source_type=SourceType.TEMPLATE.value,
                    )
                    for slug in self.categories.template_slugs()
                ]
                await self._log_user_action(user.id, "draft_loaded_template", {"items_count": len(state.draft_items)})
                return WorkflowResult(user=user, state=state, screen=self._preview_screen(state, user.language))
            raise ValidationError("errors.send_photo_or_text")
        if name == "submit_manual_text":
            state.draft_items = self.parser.parse_manual_lines(str(command.payload["text"]))
            state.pending_input_kind = None
            await self._log_user_action(user.id, "draft_loaded_manual", {"items_count": len(state.draft_items)})
            return WorkflowResult(user=user, state=state, screen=self._preview_screen(state, user.language))
        if name == "submit_photo_path":
            text = await self.ocr.extract_text(Path(str(command.payload["path"])))
            items = self.parser.parse_ocr_text(text)
            if not items:
                raise ValidationError("errors.ocr_empty")
            state.draft_items = items
            state.pending_input_kind = None
            await self._log_user_action(user.id, "draft_loaded_ocr", {"items_count": len(state.draft_items)})
            return WorkflowResult(user=user, state=state, screen=self._preview_screen(state, user.language))
        if name == "open_preview":
            return WorkflowResult(user=user, state=state, screen=self._preview_screen(state, user.language))
        if name == "add_item":
            state.pending_input_kind = "item_category_new"
            await self._log_user_action(user.id, "draft_item_add_started", {"items_count": len(state.draft_items)})
            return WorkflowResult(user=user, state=state, screen=self._item_category_prompt_screen())
        if name == "pick_item":
            idx = int(command.payload["index"])
            if idx < 0 or idx >= len(state.draft_items):
                raise ValidationError("errors.invalid_manual_input")
            state.editing_item_index = idx
            return WorkflowResult(user=user, state=state, screen=self._edit_item_screen(state.draft_items[idx], idx))
        if name == "edit_item_category":
            state.pending_input_kind = "item_category_edit"
            state.editing_item_index = int(command.payload["index"])
            await self._log_user_action(user.id, "draft_item_edit_category_started", {"index": state.editing_item_index})
            return WorkflowResult(user=user, state=state, screen=self._item_category_prompt_screen())
        if name == "edit_item_percent":
            state.pending_input_kind = "item_percent_edit"
            state.editing_item_index = int(command.payload["index"])
            await self._log_user_action(user.id, "draft_item_edit_percent_started", {"index": state.editing_item_index})
            return WorkflowResult(user=user, state=state, screen=self._item_percent_prompt_screen())
        if name == "delete_item":
            idx = int(command.payload["index"])
            if idx < 0 or idx >= len(state.draft_items):
                raise ValidationError("errors.invalid_manual_input")
            state.draft_items.pop(idx)
            await self._log_user_action(
                user.id,
                "draft_item_deleted",
                {"index": idx, "remaining_items_count": len(state.draft_items)},
            )
            return WorkflowResult(user=user, state=state, screen=self._preview_screen(state, user.language))
        if name == "submit_item_category":
            return await self._submit_item_category(user, state, str(command.payload["text"]))
        if name == "submit_item_percent":
            return await self._submit_item_percent(user, state, str(command.payload["text"]))
        if name == "save_bank":
            await self._save_bank(user.id, state)
            result = await self.execute(user, state, UserCommand(name="open_bank", payload={"id": state.selected_bank_id}))
            result.effects.append(Effect(kind="show_status", payload={"message_key": "messages.saved_bank", "transient": True}))
            return result
        if name == "cancel_flow":
            return WorkflowResult(user=user, state=WorkflowState(), screen=self._home_screen())
        if name == "open_my_banks":
            return WorkflowResult(user=user, state=state, screen=await self._my_banks_screen(user.id))
        if name == "open_bank":
            bank_id = int(command.payload["id"])
            return WorkflowResult(user=user, state=state, screen=await self._bank_details_screen(user.id, bank_id, user.language))
        if name == "edit_bank":
            aggregate = await self._load_bank_aggregate(user.id, int(command.payload["id"]))
            state.mode = "edit"
            state.selected_bank_id = aggregate.bank.id
            state.selected_bank_name = aggregate.bank.bank_name
            state.draft_items = aggregate.items
            state.pending_input_kind = None
            if aggregate.items:
                state.temp_payload["source_type"] = aggregate.items[0].source_type
            return WorkflowResult(user=user, state=state, screen=self._preview_screen(state, user.language))
        if name == "request_delete_bank":
            bank_id = int(command.payload["id"])
            return WorkflowResult(user=user, state=state, screen=await self._confirm_delete_bank_screen(user.id, bank_id))
        if name == "confirm_delete_bank":
            await self._delete_bank(user.id, int(command.payload["id"]))
            return WorkflowResult(user=user, state=WorkflowState(), screen=self._home_screen(body_key="messages.deleted_bank"))
        if name == "open_top":
            return WorkflowResult(user=user, state=state, screen=await self._top_screen(user.id, user.language))
        if name == "open_top_category":
            slug = str(command.payload["slug"])
            return WorkflowResult(user=user, state=state, screen=await self._top_category_screen(user.id, user.language, slug))
        if name == "open_settings":
            return WorkflowResult(user=user, state=state, screen=self._settings_screen(user))
        if name == "set_language":
            user = await self._set_language(user.id, str(command.payload["code"]))
            return WorkflowResult(user=user, state=state, screen=self._settings_screen(user))
        if name == "toggle_notifications":
            user = await self._toggle_notifications(user.id)
            return WorkflowResult(user=user, state=state, screen=self._settings_screen(user))
        if name == "open_history":
            return WorkflowResult(user=user, state=state, screen=await self._history_screen(user.id))
        if name == "submit_text":
            return await self._handle_text(user, state, str(command.payload["text"]))
        raise ValidationError("errors.unknown_command")

    async def _submit_item_category(self, user: UserProfile, state: WorkflowState, text: str) -> WorkflowResult:
        value = text.strip()
        if not value:
            raise ValidationError("errors.invalid_manual_input")
        normalized = self.categories.normalize(value)
        if state.pending_input_kind == "item_category_edit":
            idx = state.editing_item_index
            if idx is None or idx >= len(state.draft_items):
                raise ValidationError("errors.invalid_manual_input")
            old = state.draft_items[idx]
            state.draft_items[idx] = CashbackDraftItem(
                raw_category=value,
                normalized_category=normalized.slug,
                percent=old.percent,
                source_type=old.source_type,
            )
            await self._log_user_action(
                user.id,
                "draft_item_category_set",
                {"mode": "edit", "index": idx, "normalized_category": normalized.slug},
            )
            state.pending_input_kind = None
            return WorkflowResult(user=user, state=state, screen=self._preview_screen(state, user.language))
        state.temp_payload["pending_category"] = value
        state.temp_payload["pending_slug"] = normalized.slug
        await self._log_user_action(
            user.id,
            "draft_item_category_set",
            {"mode": "new_pending", "normalized_category": normalized.slug},
        )
        state.pending_input_kind = "item_percent_new"
        return WorkflowResult(user=user, state=state, screen=self._item_percent_prompt_screen())

    async def _submit_item_percent(self, user: UserProfile, state: WorkflowState, text: str) -> WorkflowResult:
        percent = self._parse_percent(text)
        if state.pending_input_kind == "item_percent_edit":
            idx = state.editing_item_index
            if idx is None or idx >= len(state.draft_items):
                raise ValidationError("errors.invalid_percent")
            old = state.draft_items[idx]
            state.draft_items[idx] = CashbackDraftItem(
                raw_category=old.raw_category,
                normalized_category=old.normalized_category,
                percent=percent,
                source_type=old.source_type,
            )
            await self._log_user_action(
                user.id,
                "draft_item_percent_set",
                {"mode": "edit", "index": idx, "percent": str(percent)},
            )
        else:
            category = state.temp_payload.get("pending_category")
            slug = state.temp_payload.get("pending_slug")
            source_type = state.temp_payload.get("source_type", SourceType.MANUAL.value)
            if not category or not slug:
                raise ValidationError("errors.invalid_manual_input")
            state.draft_items.append(
                CashbackDraftItem(
                    raw_category=str(category),
                    normalized_category=str(slug),
                    percent=percent,
                    source_type=str(source_type),
                )
            )
            await self._log_user_action(
                user.id,
                "draft_item_added",
                {"normalized_category": str(slug), "percent": str(percent)},
            )
            state.temp_payload.pop("pending_category", None)
            state.temp_payload.pop("pending_slug", None)
        state.pending_input_kind = None
        return WorkflowResult(user=user, state=state, screen=self._preview_screen(state, user.language))

    async def _handle_text(self, user: UserProfile, state: WorkflowState, text: str) -> WorkflowResult:
        kind = state.pending_input_kind
        if kind == "custom_bank_name":
            return await self.execute(user, state, UserCommand(name="submit_custom_bank_name", payload={"text": text}))
        if kind == "manual_lines":
            return await self.execute(user, state, UserCommand(name="submit_manual_text", payload={"text": text}))
        if kind in {"item_category_new", "item_category_edit"}:
            return await self.execute(user, state, UserCommand(name="submit_item_category", payload={"text": text}))
        if kind in {"item_percent_new", "item_percent_edit"}:
            return await self.execute(user, state, UserCommand(name="submit_item_percent", payload={"text": text}))
        best_intent = self.parser.understand_best_query(text)
        if best_intent:
            return await self.execute(
                user,
                state,
                UserCommand(name="open_top_category", payload={"slug": best_intent.normalized_category}),
            )
        delete_intent = self.parser.understand_delete_command(text)
        if delete_intent:
            if delete_intent.kind == "bank":
                await self._delete_bank_by_name(user.id, delete_intent.target)
                return WorkflowResult(user=user, state=WorkflowState(), screen=self._home_screen(body_key="messages.deleted_bank"))
            deleted_count, touched_banks = await self._delete_category(user.id, delete_intent.target)
            return WorkflowResult(
                user=user,
                state=state,
                screen=Screen(
                    id="delete_category_result",
                    title_key="screens.home",
                    body_key="messages.deleted_category",
                    body_params={"count": deleted_count, "banks": touched_banks},
                    actions=[Action(command="open_home", label_key="buttons.home")],
                ),
            )
        return WorkflowResult(
            user=user,
            state=state,
            screen=self._help_screen(),
            effects=[Effect(kind="show_status", payload={"message_key": "errors.unknown_command"})],
        )

    async def _save_bank(self, user_id: int, state: WorkflowState) -> None:
        bank_name = (state.selected_bank_name or "").strip()
        if not bank_name:
            raise ValidationError("errors.invalid_bank_name")
        if not state.draft_items:
            raise ValidationError("errors.no_items_to_save")
        if any(item.percent <= 0 for item in state.draft_items):
            raise ValidationError("errors.zero_percent_not_allowed")
        async with self.uow_factory() as uow:
            bank = await uow.banks.get_for_user(user_id, state.selected_bank_id) if state.selected_bank_id else None
            created = False
            if bank is None:
                bank = await uow.banks.get_by_name(user_id, bank_name)
            if bank is None:
                bank = await uow.banks.create(user_id, bank_name)
                created = True
            else:
                await uow.banks.update_name(bank.id, bank_name)
            await uow.cashback.replace_for_bank(bank.id, state.draft_items)
            await uow.logs.add(user_id, "bank_added" if created else "bank_updated", {"bank_id": bank.id, "bank_name": bank.bank_name})
            await uow.commit()
            state.selected_bank_id = bank.id
            state.selected_bank_name = bank.bank_name
            state.pending_input_kind = None

    async def _my_banks_screen(self, user_id: int) -> Screen:
        async with self.uow_factory() as uow:
            banks = await uow.banks.list_for_user(user_id)
        if not banks:
            return Screen(
                id="my_banks",
                title_key="screens.my_banks",
                body_key="messages.empty_banks",
                actions=[Action(command="open_home", label_key="buttons.home")],
            )
        actions = [Action(command="open_bank", label_key=f"bank:{item.bank_name}", payload={"id": item.id}) for item in banks]
        actions.append(Action(command="open_home", label_key="buttons.home"))
        return Screen(id="my_banks", title_key="screens.my_banks", body_key="screens.my_banks", actions=actions)

    async def _load_bank_aggregate(self, user_id: int, bank_id: int) -> BankAggregate:
        async with self.uow_factory() as uow:
            bank = await uow.banks.get_for_user(user_id, bank_id)
            if bank is None:
                raise NotFoundError("errors.bank_not_found")
            items = await uow.cashback.list_for_bank(bank.id)
            return BankAggregate(bank=bank, items=items)

    async def _bank_details_screen(self, user_id: int, bank_id: int, language: str) -> Screen:
        aggregate = await self._load_bank_aggregate(user_id, bank_id)
        return Screen(
            id="bank_details",
            title_key="screens.bank_details",
            body_key="screens.bank_details",
            body_params={"bank_name": aggregate.bank.bank_name, "items": self._items_lines(aggregate.items, language)},
            actions=[
                Action(command="edit_bank", label_key="buttons.edit", payload={"id": bank_id}),
                Action(command="request_delete_bank", label_key="buttons.delete", payload={"id": bank_id}, destructive=True),
                Action(command="open_home", label_key="buttons.home"),
            ],
        )

    async def _confirm_delete_bank_screen(self, user_id: int, bank_id: int) -> Screen:
        aggregate = await self._load_bank_aggregate(user_id, bank_id)
        return Screen(
            id="confirm_delete_bank",
            title_key="screens.confirm_delete_bank",
            body_key="screens.confirm_delete_bank",
            body_params={"bank_name": aggregate.bank.bank_name},
            actions=[
                Action(command="confirm_delete_bank", label_key="buttons.confirm_delete", payload={"id": bank_id}, destructive=True),
                Action(command="open_bank", label_key="buttons.back", payload={"id": bank_id}),
            ],
        )

    async def _delete_bank(self, user_id: int, bank_id: int) -> None:
        async with self.uow_factory() as uow:
            bank = await uow.banks.get_for_user(user_id, bank_id)
            if bank is None:
                raise NotFoundError("errors.bank_not_found")
            await uow.banks.delete(bank.id)
            await uow.logs.add(user_id, "bank_deleted", {"bank_id": bank.id, "bank_name": bank.bank_name})
            await uow.commit()

    async def _delete_bank_by_name(self, user_id: int, bank_name: str) -> None:
        async with self.uow_factory() as uow:
            banks = await uow.banks.list_for_user(user_id)
            if not banks:
                raise NotFoundError("errors.bank_not_found")
            matched = process.extractOne(bank_name, [item.bank_name for item in banks], score_cutoff=70)
            if not matched:
                raise NotFoundError("errors.bank_not_found")
            bank = next(item for item in banks if item.bank_name == matched[0])
            await uow.banks.delete(bank.id)
            await uow.logs.add(user_id, "bank_deleted", {"bank_id": bank.id, "bank_name": bank.bank_name})
            await uow.commit()

    async def _delete_category(self, user_id: int, query: str) -> tuple[int, int]:
        total = 0
        touched = 0
        target_slugs = self.categories.expand_query_slugs(query)
        async with self.uow_factory() as uow:
            banks = await uow.banks.list_for_user(user_id)
            for bank in banks:
                items = await uow.cashback.list_for_bank(bank.id)
                remaining = [item for item in items if item.normalized_category not in target_slugs]
                deleted = len(items) - len(remaining)
                if deleted <= 0:
                    continue
                total += deleted
                touched += 1
                await uow.cashback.replace_for_bank(bank.id, remaining)
            if total == 0:
                raise NotFoundError("errors.category_not_found")
            await uow.logs.add(user_id, "category_deleted", {"query": query, "deleted_items": total, "affected_banks": touched})
            await uow.commit()
        return total, touched

    async def _load_ranking_entries(self, user_id: int) -> list[RankingEntry]:
        entries: list[RankingEntry] = []
        async with self.uow_factory() as uow:
            banks = await uow.banks.list_for_user(user_id)
            for bank in banks:
                items = await uow.cashback.list_for_bank(bank.id)
                for item in items:
                    entries.append(
                        RankingEntry(
                            bank_id=bank.id,
                            bank_name=bank.bank_name,
                            category_slug=item.normalized_category,
                            percent=item.percent,
                        )
                    )
        return entries

    async def _top_screen(self, user_id: int, language: str) -> Screen:
        entries = await self._load_ranking_entries(user_id)
        if not entries:
            return Screen(id="top", title_key="screens.top", body_key="messages.no_ranking_data", actions=[Action(command="open_home", label_key="buttons.home")])
        leaders = self.ranking.top_by_category(entries, language)
        global_rating = self.ranking.top_global(entries, language)
        leaders_text = "\n".join(f"- {item.category_name}: {item.best_percent}% ({', '.join(item.bank_names)})" for item in leaders)
        global_text = "\n".join(f"- {item.bank_name}: {item.score}" for item in global_rating)
        actions = [Action(command="open_top_category", label_key=item.category_name, payload={"slug": item.category_slug}) for item in leaders]
        actions.append(Action(command="open_home", label_key="buttons.home"))
        return Screen(
            id="top",
            title_key="screens.top",
            body_key="screens.top",
            body_params={"leaders": leaders_text, "global_rating": global_text},
            actions=actions,
        )

    async def _top_category_screen(self, user_id: int, language: str, slug: str) -> Screen:
        entries = await self._load_ranking_entries(user_id)
        leader = self.ranking.best_for_slug(entries, slug, language)
        if leader is None:
            return Screen(
                id="top_category",
                title_key="screens.top_category",
                body_key="messages.no_ranking_data",
                actions=[Action(command="open_top", label_key="buttons.back"), Action(command="open_home", label_key="buttons.home")],
            )
        return Screen(
            id="top_category",
            title_key="screens.top_category",
            body_key="screens.top_category",
            body_params={"category": leader.category_name, "percent": leader.best_percent, "banks": ", ".join(leader.bank_names)},
            actions=[Action(command="open_top", label_key="buttons.back"), Action(command="open_home", label_key="buttons.home")],
        )

    async def _history_screen(self, user_id: int) -> Screen:
        async with self.uow_factory() as uow:
            logs = await uow.logs.list_recent(user_id, 10)
        if not logs:
            return Screen(id="history", title_key="screens.history", body_key="messages.empty_history", actions=[Action(command="open_home", label_key="buttons.home")])
        lines = "\n".join(f"- {entry.created_at.isoformat(timespec='minutes')} {entry.action}" for entry in logs)
        return Screen(id="history", title_key="screens.history", body_key="screens.history", body_params={"entries": lines}, actions=[Action(command="open_home", label_key="buttons.home")])

    async def _set_language(self, user_id: int, language: str) -> UserProfile:
        if language not in {"ru", "en"}:
            raise ValidationError("errors.invalid_language")
        async with self.uow_factory() as uow:
            await uow.users.set_language(user_id, language)
            await uow.logs.add(user_id, "language_changed", {"language": language})
            user = await uow.users.get_by_id(user_id)
            await uow.commit()
        if user is None:
            raise NotFoundError("errors.unexpected")
        return user

    async def _toggle_notifications(self, user_id: int) -> UserProfile:
        async with self.uow_factory() as uow:
            enabled = await uow.users.toggle_notifications(user_id)
            await uow.logs.add(user_id, "notifications_toggled", {"notifications_enabled": enabled})
            user = await uow.users.get_by_id(user_id)
            await uow.commit()
        if user is None:
            raise NotFoundError("errors.unexpected")
        return user

    def _home_screen(self, body_key: str = "screens.home") -> Screen:
        return Screen(
            id="home",
            title_key="screens.home",
            body_key=body_key,
            actions=[
                Action(command="open_add_bank", label_key="buttons.add_bank"),
                Action(command="open_my_banks", label_key="buttons.my_banks"),
                Action(command="open_top", label_key="buttons.top"),
                Action(command="open_settings", label_key="buttons.settings"),
                Action(command="open_history", label_key="buttons.history"),
                Action(command="open_help", label_key="buttons.help"),
            ],
        )

    def _help_screen(self) -> Screen:
        return Screen(id="help", title_key="screens.help", body_key="screens.help", actions=[Action(command="open_home", label_key="buttons.home")])

    def _choose_bank_screen(self) -> Screen:
        actions = [Action(command="select_bank_preset", label_key=name, payload={"index": idx}) for idx, name in enumerate(POPULAR_BANKS)]
        actions.append(Action(command="select_bank_other", label_key="buttons.other_bank"))
        actions.append(Action(command="open_home", label_key="buttons.home"))
        return Screen(id="choose_bank", title_key="screens.choose_bank", body_key="screens.choose_bank", actions=actions)

    def _custom_bank_prompt_screen(self) -> Screen:
        return Screen(id="custom_bank_name", title_key="screens.enter_bank_name", body_key="screens.enter_bank_name", actions=[Action(command="cancel_flow", label_key="buttons.cancel")], expects_input="custom_bank_name")

    def _input_method_screen(self, bank_name: str) -> Screen:
        return Screen(
            id="input_method",
            title_key="screens.input_method",
            body_key="screens.input_method",
            body_params={"bank_name": bank_name},
            actions=[
                Action(command="choose_input_method", label_key="buttons.input_photo", payload={"method": "photo"}),
                Action(command="choose_input_method", label_key="buttons.input_manual", payload={"method": "manual"}),
                Action(command="choose_input_method", label_key="buttons.input_template", payload={"method": "template"}),
                Action(command="cancel_flow", label_key="buttons.cancel"),
            ],
        )

    def _manual_prompt_screen(self) -> Screen:
        return Screen(id="manual_prompt", title_key="screens.manual_prompt", body_key="screens.manual_prompt", actions=[Action(command="cancel_flow", label_key="buttons.cancel")], expects_input="manual_lines")

    def _photo_prompt_screen(self) -> Screen:
        return Screen(id="photo_prompt", title_key="screens.photo_prompt", body_key="screens.photo_prompt", actions=[Action(command="cancel_flow", label_key="buttons.cancel")], expects_input="photo_upload")

    def _preview_screen(self, state: WorkflowState, language: str) -> Screen:
        actions = [Action(command="pick_item", label_key=f"{idx + 1}. {item.raw_category} ({item.percent}%)", payload={"index": idx}) for idx, item in enumerate(state.draft_items)]
        actions.extend([Action(command="add_item", label_key="buttons.add_item"), Action(command="save_bank", label_key="buttons.save"), Action(command="cancel_flow", label_key="buttons.cancel")])
        source_type = state.temp_payload.get("source_type", SourceType.MANUAL.value)
        return Screen(id="preview", title_key="screens.preview", body_key="screens.preview", body_params={"bank_name": state.selected_bank_name or "-", "items": self._items_lines(state.draft_items, language), "source_type": source_type}, actions=actions)

    def _edit_item_screen(self, item: CashbackDraftItem, idx: int) -> Screen:
        return Screen(
            id="edit_item",
            title_key="screens.choose_item_action",
            body_key="screens.choose_item_action",
            body_params={"item": item.raw_category, "percent": item.percent},
            actions=[
                Action(command="edit_item_category", label_key="buttons.edit_category", payload={"index": idx}),
                Action(command="edit_item_percent", label_key="buttons.edit_percent", payload={"index": idx}),
                Action(command="delete_item", label_key="buttons.delete", payload={"index": idx}, destructive=True),
                Action(command="open_preview", label_key="buttons.back"),
            ],
        )

    def _item_category_prompt_screen(self) -> Screen:
        return Screen(id="item_category_prompt", title_key="screens.ask_item_category", body_key="screens.ask_item_category", actions=[Action(command="open_preview", label_key="buttons.back")], expects_input="item_category")

    def _item_percent_prompt_screen(self) -> Screen:
        return Screen(id="item_percent_prompt", title_key="screens.ask_item_percent", body_key="screens.ask_item_percent", actions=[Action(command="open_preview", label_key="buttons.back")], expects_input="item_percent")

    def _settings_screen(self, user: UserProfile) -> Screen:
        notifications = "labels.notifications_on" if user.notifications_enabled else "labels.notifications_off"
        language = "labels.language_en" if user.language == "en" else "labels.language_ru"
        toggle_key = "buttons.toggle_notifications_on" if user.notifications_enabled else "buttons.toggle_notifications_off"
        return Screen(
            id="settings",
            title_key="screens.settings",
            body_key="screens.settings",
            body_params={"language": language, "notifications": notifications},
            actions=[
                Action(command="set_language", label_key="buttons.language_ru", payload={"code": "ru"}),
                Action(command="set_language", label_key="buttons.language_en", payload={"code": "en"}),
                Action(command="toggle_notifications", label_key=toggle_key),
                Action(command="open_home", label_key="buttons.home"),
            ],
        )

    def _interrupt_screen(self, state: WorkflowState) -> Screen:
        target = self._peek_interrupt_target_name(state)
        actions = [
            Action(command="continue_draft", label_key="buttons.continue_editing", variant="secondary", group="safe"),
        ]
        if self._can_save_draft(state):
            actions.append(Action(command="save_draft_and_go", label_key="buttons.save_and_continue", variant="primary", group="safe"))
        actions.append(
            Action(
                command="discard_draft_and_go",
                label_key="buttons.discard_and_continue",
                destructive=True,
                variant="danger",
                group="danger",
            )
        )
        return Screen(
            id="interrupt_flow",
            title_key="screens.interrupt_flow",
            body_key="messages.confirm_discard_draft",
            body_params={"target": self._target_label(target)},
            actions=actions,
            layout_hint="detail",
        )

    def _parse_percent(self, value: str) -> Decimal:
        try:
            percent = Decimal(value.strip().replace(",", "."))
        except InvalidOperation as error:
            raise ValidationError("errors.invalid_percent") from error
        if percent <= 0 or percent > 100:
            raise ValidationError("errors.invalid_percent")
        return percent.quantize(Decimal("0.01"))

    def _items_lines(self, items: list[CashbackDraftItem], language: str) -> str:
        if not items:
            return "-"
        return "\n".join(
            f"- {self.categories.display_name(item.normalized_category, language)} / {item.raw_category}: {item.percent}%"
            for item in items
        )

    def _should_interrupt_navigation(self, state: WorkflowState, command: UserCommand) -> bool:
        if not self._has_active_draft(state):
            return False
        if command.name in {"continue_draft", "discard_draft_and_go", "save_draft_and_go", "save_bank"}:
            return False
        return command.name in {
            "start",
            "open_home",
            "open_help",
            "open_add_bank",
            "open_my_banks",
            "open_top",
            "open_settings",
            "open_history",
            "cancel_flow",
        }

    def _has_active_draft(self, state: WorkflowState) -> bool:
        if state.draft_items:
            return True
        if state.pending_input_kind is not None:
            return True
        if state.selected_bank_id is not None:
            return True
        if bool((state.selected_bank_name or "").strip()):
            return True
        if state.editing_item_index is not None:
            return True
        return "pending_category" in state.temp_payload or "pending_slug" in state.temp_payload

    def _can_save_draft(self, state: WorkflowState) -> bool:
        bank_name = (state.selected_bank_name or "").strip()
        if not bank_name:
            return False
        if not state.draft_items:
            return False
        return all(item.percent > 0 for item in state.draft_items)

    def _set_interrupt_target(self, state: WorkflowState, command: UserCommand) -> None:
        state.temp_payload["interrupt_target_name"] = command.name
        state.temp_payload["interrupt_target_payload"] = dict(command.payload)

    def _take_interrupt_target(self, state: WorkflowState) -> UserCommand:
        target_name = self._peek_interrupt_target_name(state)
        raw_payload = state.temp_payload.pop("interrupt_target_payload", {})
        state.temp_payload.pop("interrupt_target_name", None)
        payload = raw_payload if isinstance(raw_payload, dict) else {}
        return UserCommand(name=target_name, payload=payload)

    def _peek_interrupt_target_name(self, state: WorkflowState) -> str:
        raw_name = state.temp_payload.get("interrupt_target_name")
        if isinstance(raw_name, str) and raw_name:
            return raw_name
        return "open_home"

    def _clear_interrupt_target(self, state: WorkflowState) -> None:
        state.temp_payload.pop("interrupt_target_name", None)
        state.temp_payload.pop("interrupt_target_payload", None)

    def _target_label(self, target_name: str) -> str:
        labels = {
            "open_home": "labels.target_home",
            "open_help": "labels.target_help",
            "open_add_bank": "labels.target_add_bank",
            "open_my_banks": "labels.target_my_banks",
            "open_top": "labels.target_top",
            "open_settings": "labels.target_settings",
            "open_history": "labels.target_history",
            "cancel_flow": "labels.target_cancel",
            "start": "labels.target_home",
        }
        return labels.get(target_name, "labels.target_other")

    async def _log_user_action(self, user_id: int, action: str, payload: dict[str, object] | None = None) -> None:
        try:
            async with self.uow_factory() as uow:
                await uow.logs.add(user_id, action, payload)
                await uow.commit()
        except (RuntimeError, OSError) as error:
            logger.warning("Non-blocking draft log failure for action %s: %s", action, error)
        except Exception as error:
            logger.warning("Non-blocking unexpected draft log failure for action %s: %s", action, error)
