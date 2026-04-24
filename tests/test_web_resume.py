from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.test_web_adapter import _build_client, _register


def test_web_home_resumes_persisted_draft_after_new_login_session(uow_factory, dummy_ocr, tmp_path: Path) -> None:
    first_client = _build_client(uow_factory, dummy_ocr, tmp_path)
    _register(first_client, username="resume_user", password="strongpass123")

    first_client.post("/app/action", data={"command": "open_add_bank", "payload_json": "{}"})
    first_client.post("/app/action", data={"command": "select_bank_preset", "payload_json": "{\"index\": 0}"})
    first_client.post(
        "/app/action",
        data={"command": "choose_input_method", "payload_json": "{\"method\": \"manual\"}"},
    )
    preview = first_client.post("/app/input", data={"text": "Fuel 5%\nRestaurants 7%"})
    assert preview.status_code == 200
    assert 'data-screen="preview"' in preview.text

    second_client: TestClient = _build_client(uow_factory, dummy_ocr, tmp_path)
    login = second_client.post(
        "/auth/login",
        data={"username": "resume_user", "password": "strongpass123"},
        follow_redirects=False,
    )
    assert login.status_code == 303

    resumed = second_client.get("/app")

    assert resumed.status_code == 200
    assert 'data-screen="preview"' in resumed.text
    assert 'name="command" value="save_bank"' in resumed.text
