from __future__ import annotations

import asyncio
import hashlib
import hmac
import io
import time
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from app.adapters.auth_local import Argon2PasswordHasher
from app.adapters.system import NoopReminderSender, SystemClock
from app.adapters.web.app import WebDependencies, create_web_app
from app.application import ApplicationFacade
from app.application.auth.use_cases import (
    AuthenticateExternalIdentityUseCase,
    AuthenticateLocalUserUseCase,
    GetUserAccountUseCase,
    LinkExternalIdentityUseCase,
    ListExternalIdentitiesUseCase,
    RegisterLocalUserUseCase,
    UnlinkExternalIdentityUseCase,
)
from app.application.use_cases.best_card_for_category import BestCardForCategoryUseCase
from app.application.use_cases.find_user_by_identity import FindUserByExternalIdentityUseCase
from app.application.use_cases.get_ranking import GetRankingUseCase
from app.application.use_cases.handle_command import HandleCommandUseCase
from app.application.use_cases.ranking_snapshot import RankingSnapshotUseCase
from app.application.use_cases.log_event import LogEventUseCase
from app.application.use_cases.quick_add_bank import QuickAddBankUseCase
from app.application.use_cases.save_bank_draft import SaveBankDraftUseCase
from app.application.use_cases.send_monthly_reminders import SendMonthlyRemindersUseCase
from app.application.use_cases.sync_user import SyncTelegramUserUseCase
from app.domain.services.categories import CategoryService
from app.domain.services.parsing import ParserService
from app.domain.services.ranking import RankingService
from app.i18n.localizer import Localizer


def _build_facade(uow_factory, dummy_ocr) -> ApplicationFacade:
    categories = CategoryService()
    parser = ParserService(categories)
    ranking = RankingService(categories)
    password_hasher = Argon2PasswordHasher()
    return ApplicationFacade(
        RegisterLocalUserUseCase(uow_factory, password_hasher, default_language="ru"),
        AuthenticateLocalUserUseCase(uow_factory, password_hasher),
        AuthenticateExternalIdentityUseCase(uow_factory, default_language="ru"),
        LinkExternalIdentityUseCase(uow_factory),
        UnlinkExternalIdentityUseCase(uow_factory),
        GetUserAccountUseCase(uow_factory),
        ListExternalIdentitiesUseCase(uow_factory),
        SyncTelegramUserUseCase(uow_factory, default_language="ru"),
        HandleCommandUseCase(
            uow_factory=uow_factory,
            parser=parser,
            categories=categories,
            ranking=ranking,
            ocr=dummy_ocr,
        ),
        SendMonthlyRemindersUseCase(
            uow_factory=uow_factory,
            sender=NoopReminderSender(),
            clock=SystemClock("Europe/Moscow"),
            reminder_hour=10,
        ),
        LogEventUseCase(uow_factory),
        FindUserByExternalIdentityUseCase(uow_factory),
        BestCardForCategoryUseCase(uow_factory, ranking, categories),
        QuickAddBankUseCase(parser, SaveBankDraftUseCase(uow_factory)),
        GetRankingUseCase(uow_factory, ranking),
        RankingSnapshotUseCase(uow_factory, ranking, categories),
    )


def _build_client(uow_factory, dummy_ocr, tmp_path: Path, *, telegram_auth_enabled: bool = True) -> TestClient:
    locales_dir = Path(__file__).resolve().parents[1] / "app" / "locales"
    deps = WebDependencies(
        facade=_build_facade(uow_factory, dummy_ocr),
        localizer=Localizer(locales_dir=locales_dir, default_language="ru"),
        default_language="ru",
        temp_dir=tmp_path / "temp",
        bot_token="123456:valid_token",
        bot_username="cashback_analyzer_bot",
        telegram_auth_enabled=telegram_auth_enabled,
        web_base_url="http://testserver",
        max_upload_size=1024 * 1024,
        secure_cookies=False,
        session_secret="test-session-secret",
    )
    return TestClient(create_web_app(deps))


def _sign_payload(payload: dict[str, str], bot_token: str) -> dict[str, str]:
    data_check_string = "\n".join(f"{key}={payload[key]}" for key in sorted(payload))
    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
    signature = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    signed = dict(payload)
    signed["hash"] = signature
    return signed


def _register(client: TestClient, *, username: str = "demo_user", password: str = "strongpass123") -> None:
    response = client.post(
        "/auth/register",
        data={"display_name": "Demo User", "username": username, "email": "", "password": password},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/app"


def test_web_local_register_and_manual_flow(uow_factory, dummy_ocr, tmp_path: Path) -> None:
    client = _build_client(uow_factory, dummy_ocr, tmp_path)
    _register(client)

    home = client.get("/app")
    assert home.status_code == 200
    assert "Cashback Analyzer" in home.text
    assert "viewport-fit=cover" in home.text

    client.post("/app/action", data={"command": "open_add_bank", "payload_json": "{}"})
    client.post("/app/action", data={"command": "select_bank_preset", "payload_json": "{\"index\": 0}"})
    manual_prompt = client.post(
        "/app/action",
        data={"command": "choose_input_method", "payload_json": "{\"method\": \"manual\"}"},
    )
    assert manual_prompt.status_code == 200
    assert "<textarea" in manual_prompt.text

    preview = client.post("/app/input", data={"text": "Fuel 5%\nRestaurants 7%"})
    assert preview.status_code == 200
    assert 'name="command" value="save_bank"' in preview.text

    saved = client.post("/app/action", data={"command": "save_bank", "payload_json": "{}"})
    assert saved.status_code == 200
    assert "T-Bank" in saved.text


def test_web_photo_flow_uses_bytes_upload_contract(uow_factory, dummy_ocr, tmp_path: Path) -> None:
    dummy_ocr.value = ""
    client = _build_client(uow_factory, dummy_ocr, tmp_path)
    _register(client)

    client.post("/app/action", data={"command": "open_add_bank", "payload_json": "{}"})
    client.post("/app/action", data={"command": "select_bank_preset", "payload_json": "{\"index\": 0}"})
    client.post("/app/action", data={"command": "choose_input_method", "payload_json": "{\"method\": \"photo\"}"})

    buffer = io.BytesIO()
    Image.new("RGB", (60, 30), color="white").save(buffer, format="PNG")
    buffer.seek(0)
    response = client.post("/app/upload", files={"file": ("screen.png", buffer.getvalue(), "image/png")})

    assert response.status_code == 200
    assert "Подсказка" in response.text or "Hint" in response.text
    assert "распознать текст" in response.text or "recognize text" in response.text


def test_web_telegram_callback_resolves_linked_identity(uow_factory, dummy_ocr, tmp_path: Path, store) -> None:
    client = _build_client(uow_factory, dummy_ocr, tmp_path)

    async def _seed() -> None:
        async with uow_factory() as uow:
            user = await uow.users.create(display_name="Telegram User", default_language="ru")
            await uow.identities.upsert_for_user(
                user_id=user.id,
                provider="telegram",
                provider_user_id="42",
                provider_username="tg_user",
                provider_display_name="Telegram User",
            )
            await uow.commit()

    asyncio.run(_seed())

    response = client.get(
        "/auth/telegram/callback",
        params=_sign_payload(
            {
                "id": "42",
                "username": "tg_user",
                "first_name": "Telegram",
                "last_name": "User",
                "auth_date": str(int(time.time())),
            },
            "123456:valid_token",
        ),
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/app"
    assert any(identity.provider_user_id == "42" for identity in store.identities.values())


def test_web_telegram_callback_rejects_unlinked_identity(uow_factory, dummy_ocr, tmp_path: Path) -> None:
    client = _build_client(uow_factory, dummy_ocr, tmp_path)

    response = client.get(
        "/auth/telegram/callback",
        params=_sign_payload(
            {
                "id": "777",
                "username": "new_tg",
                "first_name": "New",
                "last_name": "Telegram",
                "auth_date": str(int(time.time())),
            },
            "123456:valid_token",
        ),
        follow_redirects=False,
    )

    assert response.status_code == 401
    assert "не привязан" in response.text or "not linked" in response.text


def test_authenticated_user_can_link_and_unlink_telegram(uow_factory, dummy_ocr, tmp_path: Path, store) -> None:
    client = _build_client(uow_factory, dummy_ocr, tmp_path)
    _register(client, username="link_user")

    callback = client.get(
        "/auth/telegram/callback",
        params=_sign_payload(
            {
                "id": "999",
                "username": "linked_tg",
                "first_name": "Linked",
                "last_name": "User",
                "auth_date": str(int(time.time())),
            },
            "123456:valid_token",
        ),
        follow_redirects=False,
    )

    assert callback.status_code == 303
    assert any(identity.provider == "telegram" and identity.provider_user_id == "999" for identity in store.identities.values())

    unlink = client.post("/auth/telegram/unlink", follow_redirects=False)
    assert unlink.status_code == 303
    assert all(identity.provider_user_id != "999" for identity in store.identities.values())
