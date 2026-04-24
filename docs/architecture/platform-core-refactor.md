# Platform Core Refactor

## Goal

Move the product from a Telegram-centered implementation to a platform-core architecture where web becomes the primary surface at the core-model level and Telegram becomes a thin secondary adapter.

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

- reminder delivery now uses `DeliveryTarget`
- targets are resolved through linked identities
- reminder loop lifecycle is owned by runtime/bootstrap rather than Telegram polling

Result:

- reminder delivery is adapter-aware without making Telegram a core concept
- Telegram remains the delivery implementation without owning scheduler lifecycle

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

### 8. Workflow decomposition completed

Delivered:

- `app/application/workflow`
- `app/application/presenters`
- thin `HandleCommandUseCase` wrapper over `WorkflowDispatcher`
- split workflow modules for draft, bank, navigation, text intents, and interrupts
- iterative dispatcher flow instead of recursive workflow self-execution

Result:

- workflow orchestration is no longer trapped in a single monolith
- presentation logic is no longer mixed with orchestration
- regression coverage can target workflow modules directly

## Validation Completed

- boundary tests verify application/domain do not import adapters/frameworks
- boundary tests verify workflow/presenters do not pull persistence concerns directly
- web boundary test verifies `app.adapters.web` does not import Telegram adapter code
- runtime tests verify reminder loop ownership is outside Telegram adapter startup
- web auth tests cover Telegram verification and local auth behavior
- workflow tests cover decomposition, interrupts, presenters, and text intent routing
- OCR tests verify bytes-based upload contract
- reminder tests verify provider-configured delivery
- integration tests cover link and unlink flows

Executed verification:

- `pytest -q`
- `python -m compileall app tests`
- `docker compose config -q`

## Residual Debt

The core refactor is complete for identity, workflow split, and adapter boundaries.
The remaining debt is narrower:

- `draft.py` is now the largest workflow module and should be kept scoped
- legacy Telegram columns still exist in persistence as a compatibility seam
- some docs still needed synchronization after the workflow split
- only Telegram reminder delivery implementation exists today; additional providers remain future work

## Compatibility Position

- Telegram bot support remains intact
- existing Telegram users are backfilled into `user_identities`
- web can operate independently from Telegram
- Telegram login on the web is link-aware instead of being the only identity source
- legacy Telegram columns remain only as a persistence compatibility seam, not as the authoritative identity source
