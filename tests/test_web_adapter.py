from __future__ import annotations

import hashlib
import hmac
import io
import time
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from app.adapters.system import NoopReminderSender, SystemClock
from app.adapters.telegram.localizer import Localizer
from app.adapters.web import WebDependencies, create_web_app
from app.application import ApplicationFacade
from app.application.use_cases.handle_command import HandleCommandUseCase
from app.application.use_cases.log_event import LogEventUseCase
from app.application.use_cases.send_monthly_reminders import SendMonthlyRemindersUseCase
from app.application.use_cases.sync_user import SyncTelegramUserUseCase
from app.domain.services.categories import CategoryService
from app.domain.services.parsing import ParserService
from app.domain.services.ranking import RankingService


def _build_facade(uow_factory, dummy_ocr) -> ApplicationFacade:
    categories = CategoryService()
    parser = ParserService(categories)
    ranking = RankingService(categories)
    sync = SyncTelegramUserUseCase(uow_factory, default_language="ru")
    handle = HandleCommandUseCase(
        uow_factory=uow_factory,
        parser=parser,
        categories=categories,
        ranking=ranking,
        ocr=dummy_ocr,
    )
    reminders = SendMonthlyRemindersUseCase(
        uow_factory=uow_factory,
        sender=NoopReminderSender(),
        clock=SystemClock("Europe/Moscow"),
        reminder_hour=10,
    )
    logs = LogEventUseCase(uow_factory)
    return ApplicationFacade(sync, handle, reminders, logs)


def _sign_payload(payload: dict[str, str], bot_token: str) -> dict[str, str]:
    data_check_string = "\n".join(f"{key}={payload[key]}" for key in sorted(payload))
    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
    signature = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    signed = dict(payload)
    signed["hash"] = signature
    return signed


def _login(client: TestClient, bot_token: str) -> None:
    payload = {
        "id": "1001",
        "username": "demo_user",
        "first_name": "Demo",
        "last_name": "User",
        "auth_date": str(int(time.time())),
    }
    signed = _sign_payload(payload, bot_token)
    response = client.get("/auth/telegram/callback", params=signed, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/app"


def test_web_manual_flow_mobile_first(uow_factory, dummy_ocr, tmp_path: Path) -> None:
    facade = _build_facade(uow_factory, dummy_ocr)
    locales_dir = Path(__file__).resolve().parents[1] / "app" / "locales"
    localizer = Localizer(locales_dir=locales_dir, default_language="ru")
    bot_token = "123456:valid_token"
    deps = WebDependencies(
        facade=facade,
        localizer=localizer,
        default_language="ru",
        temp_dir=tmp_path / "temp",
        bot_token=bot_token,
        bot_username="cashback_analyzer_bot",
        web_base_url="http://testserver",
        max_upload_size=1024 * 1024,
        secure_cookies=False,
        session_secret="test-session-secret",
    )
    app = create_web_app(deps)
    client = TestClient(app)
    _login(client, bot_token)

    home = client.get("/app")
    assert home.status_code == 200
    assert "Cashback Analyzer" in home.text
    assert "viewport-fit=cover" in home.text

    choose_bank = client.post("/app/action", data={"command": "open_add_bank", "payload_json": "{}"})
    assert choose_bank.status_code == 200
    assert "Выбор банка" in choose_bank.text

    input_method = client.post(
        "/app/action",
        data={"command": "select_bank_preset", "payload_json": '{"index": 0}'},
    )
    assert input_method.status_code == 200
    assert "Метод ввода" in input_method.text

    manual_prompt = client.post(
        "/app/action",
        data={"command": "choose_input_method", "payload_json": '{"method": "manual"}'},
    )
    assert manual_prompt.status_code == 200
    assert manual_prompt.text.count('action="/app/input"') == 1
    assert "<textarea" in manual_prompt.text

    preview = client.post("/app/input", data={"text": "АЗС 5%\nРестораны 7%"})
    assert preview.status_code == 200
    assert "Предпросмотр" in preview.text
    assert 'name="command" value="save_bank"' in preview.text

    saved = client.post("/app/action", data={"command": "save_bank", "payload_json": "{}"})
    assert saved.status_code == 200
    assert "Банк: T-Bank" in saved.text


def test_web_photo_flow_error_shows_ocr_hint(uow_factory, dummy_ocr, tmp_path: Path) -> None:
    dummy_ocr.value = ""
    facade = _build_facade(uow_factory, dummy_ocr)
    locales_dir = Path(__file__).resolve().parents[1] / "app" / "locales"
    localizer = Localizer(locales_dir=locales_dir, default_language="ru")
    bot_token = "123456:valid_token"
    deps = WebDependencies(
        facade=facade,
        localizer=localizer,
        default_language="ru",
        temp_dir=tmp_path / "temp",
        bot_token=bot_token,
        bot_username="cashback_analyzer_bot",
        web_base_url="http://testserver",
        max_upload_size=1024 * 1024,
        secure_cookies=False,
        session_secret="test-session-secret",
    )
    app = create_web_app(deps)
    client = TestClient(app)
    _login(client, bot_token)

    client.post("/app/action", data={"command": "open_add_bank", "payload_json": "{}"})
    client.post("/app/action", data={"command": "select_bank_preset", "payload_json": '{"index": 0}'})
    photo_prompt = client.post(
        "/app/action",
        data={"command": "choose_input_method", "payload_json": '{"method": "photo"}'},
    )
    assert photo_prompt.status_code == 200
    assert 'type="file"' in photo_prompt.text

    buffer = io.BytesIO()
    Image.new("RGB", (60, 30), color="white").save(buffer, format="PNG")
    buffer.seek(0)

    upload = client.post(
        "/app/upload",
        files={"file": ("screen.png", buffer.getvalue(), "image/png")},
    )
    assert upload.status_code == 200
    assert "Не удалось распознать текст" in upload.text
    assert "Подсказка: обрежьте скрин" in upload.text


def test_web_mobile_css_tokens_and_breakpoints(uow_factory, dummy_ocr, tmp_path: Path) -> None:
    facade = _build_facade(uow_factory, dummy_ocr)
    locales_dir = Path(__file__).resolve().parents[1] / "app" / "locales"
    localizer = Localizer(locales_dir=locales_dir, default_language="ru")
    deps = WebDependencies(
        facade=facade,
        localizer=localizer,
        default_language="ru",
        temp_dir=tmp_path / "temp",
        bot_token="123456:valid_token",
        bot_username="cashback_analyzer_bot",
        web_base_url="http://testserver",
        max_upload_size=1024 * 1024,
        secure_cookies=False,
        session_secret="test-session-secret",
    )
    app = create_web_app(deps)
    client = TestClient(app)

    css_response = client.get("/static/web.css")
    assert css_response.status_code == 200
    css = css_response.text
    assert "@media (max-width: 480px)" in css
    assert "env(safe-area-inset-bottom)" in css
    assert "min-height: 46px" in css


def test_web_interrupt_when_navigating_away_from_pending_manual_input(uow_factory, dummy_ocr, tmp_path: Path) -> None:
    facade = _build_facade(uow_factory, dummy_ocr)
    locales_dir = Path(__file__).resolve().parents[1] / "app" / "locales"
    localizer = Localizer(locales_dir=locales_dir, default_language="ru")
    bot_token = "123456:valid_token"
    deps = WebDependencies(
        facade=facade,
        localizer=localizer,
        default_language="ru",
        temp_dir=tmp_path / "temp",
        bot_token=bot_token,
        bot_username="cashback_analyzer_bot",
        web_base_url="http://testserver",
        max_upload_size=1024 * 1024,
        secure_cookies=False,
        session_secret="test-session-secret",
    )
    app = create_web_app(deps)
    client = TestClient(app)
    _login(client, bot_token)

    client.post("/app/action", data={"command": "open_add_bank", "payload_json": "{}"})
    client.post("/app/action", data={"command": "select_bank_preset", "payload_json": '{"index": 0}'})
    manual_prompt = client.post(
        "/app/action",
        data={"command": "choose_input_method", "payload_json": '{"method": "manual"}'},
    )
    assert manual_prompt.status_code == 200

    interrupted = client.post("/app/action", data={"command": "open_home", "payload_json": "{}"})
    assert interrupted.status_code == 200
    assert "interrupt_flow" in interrupted.text
    assert 'name="command" value="continue_draft"' in interrupted.text
    assert 'name="command" value="discard_draft_and_go"' in interrupted.text
