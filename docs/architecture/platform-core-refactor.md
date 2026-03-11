# Platform Core Refactor

## Goal

Move the product from a Telegram-centered implementation to a platform-core architecture where web becomes the primary surface and Telegram becomes a thin secondary adapter.

## Delivered Changes

### 1. Shared i18n extracted out of Telegram

Delivered:

- `app/i18n/localizer.py`
- Telegram and web now import the same localizer
- direct `web -> telegram` dependency removed

Result:

- localization is now platform-level infrastructure
- adapter boundaries are cleaner and enforceable by tests

### 2. Platform identity model introduced

Delivered:

- `users.display_name`
- nullable `users.telegram_user_id`
- `user_identities`
- `local_credentials`
- Alembic migration `20260311_0002_platform_identity.py`

Result:

- the canonical user is now a platform account
- external identities are additive, not structural
- local credentials and Telegram identities can coexist

### 3. Web-first auth implemented

Delivered:

- local registration and login use cases
- local auth adapter with secure password hashing
- web routes for register, login, logout
- Telegram link and unlink flow from authenticated web sessions

Result:

- web no longer requires Telegram as the only way in
- Telegram becomes an optional linked identity

### 4. External auth isolated

Delivered:

- `app/adapters/auth_telegram`
- `AuthenticateExternalIdentityUseCase`
- `LinkExternalIdentityUseCase`
- `UnlinkExternalIdentityUseCase`

Result:

- Telegram verification is isolated from transport rendering
- auth behavior is reusable by multiple adapters

### 5. OCR contract made transport-neutral

Delivered:

- `ImageUpload` DTO in `app/application/dto`
- `OCRPort.extract_text(upload: ImageUpload)`
- web and Telegram adapters now provide upload bytes rather than filesystem semantics

Result:

- the application layer no longer depends on `Path`
- temporary file handling is kept inside adapters

### 6. Reminder routing decoupled from Telegram column

Delivered:

- reminder delivery now uses `ReminderTarget`
- targets are resolved through linked identities

Result:

- reminder delivery is adapter-aware without making Telegram a core concept

### 7. Business use cases extracted from the workflow surface

Delivered:

- dedicated use cases for:
  - user banks
  - bank details
  - history
  - uploaded image processing
  - auth and identity operations

Result:

- more logic is now independently testable
- adapters consume a broader, cleaner facade

## Validation Completed

- boundary tests verify application/domain do not import adapters/frameworks
- web boundary test verifies `app.adapters.web` does not import Telegram adapter code
- web auth tests cover Telegram verification and local auth behavior
- OCR tests verify bytes-based upload contract
- reminder tests verify target-based delivery
- integration tests cover link and unlink flows

Executed verification:

- `pytest -q`
- `python -m compileall app tests`
- `docker compose config -q`

## Remaining Gap

The refactor is functionally complete for identity, adapter boundaries, and web-first delivery, but the workflow layer is not yet fully decomposed.

Current state:

- `HandleCommandUseCase` still acts as the central scenario dispatcher
- it delegates more work than before, but it is still larger than the desired final shape

Desired next wave:

- create `app/application/workflow`
- move scenario routing and screen assembly into smaller modules
- leave `HandleCommandUseCase` as a thin orchestration facade or remove it entirely

## Compatibility Position

- Telegram bot support remains intact
- existing Telegram users are backfilled into `user_identities`
- web can now operate independently from Telegram
- Telegram login on the web is now link-aware instead of being the only identity source
