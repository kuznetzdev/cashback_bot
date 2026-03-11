# Repository Integrity Audit

Date: 2026-03-11

## 1. Executive summary

### Overall verdict

The repository is internally coherent and materially improved by the platform-core refactor and workflow decomposition. The codebase is now centered on a transport-neutral application core with a platform identity model, transport-neutral workflow contracts, and two adapters that consume the same facade.

The strongest claims are true in substance:

- Telegram is no longer the canonical identity model.
- Web no longer depends on Telegram adapter internals.
- Workflow orchestration is no longer trapped inside one monolithic `handle_command.py`.
- Presentation helpers are separated from workflow state mutation.
- Reminder delivery no longer depends on `users.telegram_user_id` as the source of truth.

The strongest caveats are also real:

- the repository is web-first by architecture, but not by default runtime configuration
- several documents still describe the pre-decomposition state
- legacy Telegram compatibility fields and aliases remain in persistence/domain as transitional seams
- `draft.py` is the new main workflow hotspot and should be watched for re-monolithization

### Confidence level

High for architecture coherence and runtime wiring.

Moderate-high for migration correctness and operational safety, because schema/tests align well, but migration/backfill behavior is not deeply regression-tested against real upgraded datasets beyond code-level inspection and unit/integration coverage.

### Safe to continue building on?

Yes, with caveats. The repository is in a state that supports further development without immediate architectural rollback risk. The most important next step is not another broad refactor; it is tightening documentation, preserving current boundaries, and paying down the remaining compatibility seams deliberately.

### Expectation match

Expected state vs reality:

- platform-oriented core exists: verified
- identity/auth refactor exists: verified
- shared i18n no longer lives under Telegram adapter: verified
- web does not depend on Telegram adapter internals: verified
- OCR upload is bytes-based: verified
- reminders are identity-target based: verified
- workflow decomposition exists under `app/application/workflow`: verified
- presentation helpers exist under `app/application/presenters`: verified
- `handle_command.py` is a thin wrapper: verified
- recursive workflow self-execution removed: verified
- facade contract remained stable: verified
- docs fully updated: false, partially stale
- repository is operationally web-first by default config: false, only architecturally so

## 2. Repository map

### Top-level structure

- `app/`: primary runtime code
- `alembic/`: schema migrations
- `docs/`: architecture, runbook, migration, flow, and product docs
- `tests/`: unit/integration/boundary/runtime coverage
- `docker-compose.yml`, `Dockerfile`: local/runtime packaging
- `README.md`, `README.ru.md`: top-level orientation

### Application topology

- `app/domain`: pure business models and services
- `app/application`: use cases, auth, ports, facade, workflow, presenters
- `app/adapters`: PostgreSQL, auth, OCR, Telegram, web, scheduler, system
- `app/bootstrap`: settings, DI, runtime, migrations, startup checks
- `app/i18n`, `app/locales`: shared localization infrastructure

### Architectural anchors

Core entry and wiring:

- `app/main.py`
- `app/bootstrap/runtime.py`
- `app/bootstrap/container.py`
- `app/application/facade.py`

Workflow and presentation:

- `app/application/workflow/dispatcher.py`
- `app/application/workflow/models.py`
- `app/application/workflow/draft.py`
- `app/application/workflow/banks.py`
- `app/application/workflow/navigation.py`
- `app/application/workflow/text_intents.py`
- `app/application/workflow/interrupts.py`
- `app/application/presenters/workflow_screens.py`
- `app/application/presenters/workflow_formatters.py`

Identity/auth:

- `app/application/auth/use_cases.py`
- `app/domain/models.py`
- `app/adapters/postgres/models.py`
- `app/adapters/postgres/repositories.py`

Adapters:

- `app/adapters/web/app.py`
- `app/adapters/telegram/router.py`
- `app/adapters/telegram/renderer.py`
- `app/adapters/ocr_tesseract/service.py`

### Transitional and compatibility areas

- `app/application/models.py`: transitional re-export shim for workflow contracts
- `app/domain/models.py`: `UserProfile = UserAccount` compatibility alias
- `app/adapters/postgres/models.py`: legacy `users.telegram_user_id`, `username`, `full_name` still exist
- `app/adapters/postgres/repositories.py`: Telegram identity still mirrors into legacy user columns
- stale docs in `docs/ARCHITECTURE.md`, `docs/architecture/platform-core-refactor.md`, `docs/migrations/identity-clean-break.md`

### Highest-complexity modules

By line count in inspected areas:

- `app/adapters/web/app.py`: 666 lines
- `app/adapters/postgres/repositories.py`: 375 lines
- `app/adapters/telegram/router.py`: 289 lines
- `app/application/workflow/draft.py`: 277 lines

Interpretation:

- `web/app.py` is the largest adapter and now owns significant HTTP/session/render orchestration
- `repositories.py` is the densest persistence module and contains the main legacy compatibility behavior
- `draft.py` is the largest workflow scenario module and the most likely future concentration point

## 3. Architecture boundary audit

### Verified boundaries

The following boundaries are real in code, not just described in docs:

- domain code is framework-free in inspected modules
- application/use cases do not import adapter packages
- workflow modules do not import FastAPI, aiogram, SQLAlchemy, or adapter packages
- presenters are transport-neutral and only build `Screen`/string content
- web adapter does not import Telegram adapter modules
- shared localizer lives in `app/i18n/localizer.py`
- workflow no longer receives `UnitOfWorkPort` or `uow_factory` directly

`tests/test_architecture_boundaries.py` enforces part of this structurally.

### Remaining leaks or fragile seams

#### 1. Transitional identity compatibility in persistence

`app/adapters/postgres/repositories.py` still mirrors Telegram identity data into legacy user columns when provider is `telegram`:

- sets `users.telegram_user_id`
- sets `users.username`
- sets `users.full_name`
- clears them on unlink

This does not violate application/workflow boundaries, but it means Telegram-centric legacy fields still exist in the persistence model and remain behaviorally active.

#### 2. Transitional alias in domain

`app/domain/models.py` still exposes `UserProfile = UserAccount`. This is harmless today but should remain temporary. It weakens terminology clarity.

#### 3. Transitional re-export shim in application

`app/application/models.py` re-exports workflow contracts and marks them as transitional. This is acceptable and explicitly documented in code, but it is a temporary coupling seam and should not become permanent.

#### 4. Workflow logging helper catches broad exceptions

`app/application/workflow/dependencies.py` uses non-blocking logging and catches broad exceptions for workflow audit logging. This is better than silently swallowing errors, but it is still a broad operational seam. It is acceptable for secondary logging, not for core state mutation.

### “Allowed but fragile” patterns

- architecture is enforced partly by token/content tests, not by a stronger import graph tool
- workflow dispatcher remains the single routing chokepoint by design
- adapter independence is strong at code boundary level, but operational defaults still favor Telegram startup

## 4. Runtime flow map

### 4.1 Web auth flow

Entrypoints:

- `GET /`
- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/logout`
- `GET /auth/telegram/callback`
- `POST /auth/telegram/unlink`

Main path:

`app/adapters/web/app.py` -> `ApplicationFacade` -> auth use cases in `app/application/auth/use_cases.py` -> repositories/UoW -> session update in web adapter

State mutation:

- creates `users` + `local_credentials` for local registration
- links/unlinks `user_identities` for Telegram callback/link flow
- stores `web_user_id`, serialized workflow state, and current screen in session

Render boundary:

- web adapter renders transport-neutral `Screen` into HTML

### 4.2 Web manual bank entry flow

Entrypoints:

- `POST /app/action`
- `POST /app/input`

Main path:

web action -> `UserCommand` -> `ApplicationFacade.handle_command` -> `HandleCommandUseCase` -> `WorkflowDispatcher` -> `draft.py` -> `ParseManualCashbackUseCase` / `SaveBankDraftUseCase`

State mutation:

- `WorkflowState` tracks selected bank, pending input, draft items
- persistence changes occur only on `save_bank`

Render boundary:

- `workflow_screens.preview_screen(...)` -> web HTML renderer

### 4.3 Web image upload / OCR flow

Entrypoint:

- `POST /app/upload`

Main path:

web upload handler -> `ImageUpload(content: bytes, filename, content_type)` -> `submit_uploaded_image` command -> `draft.py` -> `ProcessUploadedImageUseCase.execute(upload)` -> `OCRPort.extract_text(upload)` -> parser -> preview screen

State mutation:

- workflow draft is populated from OCR result before save
- persistent state changes only on `save_bank`

Storage/external touchpoints:

- OCR adapter
- database only when final save happens

### 4.4 Telegram `/start` flow

Entrypoint:

- Telegram message `/start`

Main path:

`app/adapters/telegram/router.py` -> `SyncTelegramUserUseCase` / external identity auth -> `ApplicationFacade.handle_command(UserCommand("start"))` -> dispatcher/navigation -> `Screen` -> telegram renderer

State mutation:

- creates or restores platform user via external identity auth
- Telegram adapter stores workflow state via its own adapter state helper

Render boundary:

- `app/adapters/telegram/renderer.py`

### 4.5 Telegram callback/button flow

Entrypoint:

- inline keyboard callback data

Main path:

callback mapper in `app/adapters/telegram/callbacks.py` -> `UserCommand` -> facade -> dispatcher -> screen renderer

Important invariant:

- callback wire protocol remains adapter-owned and stable relative to workflow contracts

### 4.6 Workflow orchestration flow

Main path:

`ApplicationFacade.handle_command` -> `HandleCommandUseCase.execute` -> `WorkflowDispatcher.execute`

Dispatcher responsibilities:

- handle interrupt commands
- guard navigation when draft is active
- route free text through `text_intents.py`
- route scenario commands to `draft.py`, `banks.py`, `navigation.py`
- append queued transient effects

Important confirmation:

- no recursive self-execution remains in the main workflow engine
- iterative `while True` loop now handles save/discard/continue transitions

### 4.7 Bank save/edit/delete flow

Modules:

- `draft.py`
- `banks.py`
- `SaveBankDraftUseCase`
- `GetBankDetailsUseCase`
- `DeleteBankUseCase`

State mutation:

- draft edits remain in `WorkflowState`
- `save_bank` commits aggregate to persistence
- delete confirmation is separate and adapter-neutral

### 4.8 Ranking/history/settings flow

Modules:

- `navigation.py`
- `GetRankingUseCase`
- `GetHistoryUseCase`
- `ChangeLanguageUseCase`
- `ToggleNotificationsUseCase`

These are now clearly read/update flows outside the old monolith.

### 4.9 Interrupt flow

Modules:

- `interrupts.py`
- `dispatcher.py`
- presenters interrupt screen

Behavior:

- active draft or pending input blocks safe navigation
- `continue_draft`, `discard_draft_and_go`, `save_draft_and_go` are explicit commands
- target command is stored in workflow state and then consumed

### 4.10 Reminder flow

Main path:

runtime -> `ReminderLoop` -> `ApplicationFacade.send_monthly_reminders()` -> `SendMonthlyRemindersUseCase` -> `uow.identities.list_reminder_targets(provider="telegram")` -> reminder sender adapter -> log dedupe via `user_logs`

Important conclusion:

- delivery address no longer comes from `users.telegram_user_id`
- reminder system is still operationally Telegram-specific today because current sender/provider query is Telegram-only

### 4.11 Identity resolution / linking flow

Main paths:

- bot-first external auth: creates or restores user on Telegram contact
- web callback for linked identity: authenticates existing linked account
- web callback inside authenticated session: links Telegram identity to existing platform user
- unlink flow prevents removing the last identity when no local credentials exist

### 4.12 Migration/backfill assumptions

Migration `20260311_0002_platform_identity.py`:

- adds `users.display_name`
- makes `users.telegram_user_id` nullable
- creates `user_identities`
- backfills Telegram identities from legacy user rows
- creates `local_credentials`

The codebase still tolerates legacy Telegram columns, which is consistent with the migration’s compatibility posture.

## 5. Workflow decomposition audit

### What is verified

- `app/application/use_cases/handle_command.py` is now a thin wrapper
- workflow contracts live in `app/application/workflow/models.py`
- screen/formatting logic lives in presenters
- main orchestration moved into `WorkflowDispatcher`
- scenario logic is split across dedicated workflow modules
- interrupt policy is isolated
- text-intent routing is isolated
- recursive workflow execution has been removed

### Quality assessment

The decomposition is genuinely successful. The previous monolith was not merely renamed; responsibilities are visibly redistributed:

- orchestration: `dispatcher.py`
- draft mutation: `draft.py`
- bank navigation/delete: `banks.py`
- general navigation and read flows: `navigation.py`
- free-text routing: `text_intents.py`
- presentation: `workflow_screens.py`, `workflow_formatters.py`

### Residual workflow debt

#### 1. `draft.py` is now the hotspot

At 277 lines, `draft.py` is the densest workflow module and contains the most mutable state transitions. It is still reasonably scoped, but it is the first candidate to watch for future growth.

#### 2. Dispatcher remains central by design

`dispatcher.py` is acceptably thin, but it is still the main workflow choke point. That is not a defect today; it is simply the place where discipline must be preserved.

#### 3. Presenters are clean

Inspected presenter modules only build `Screen`/formatting output. No use-case calls or state mutation were found.

### Verdict on decomposition completeness

Complete enough to treat the old workflow-monolith problem as solved for this phase.

Not “final forever”: the next risk is growth inside `draft.py`, not regression into `handle_command.py`.

## 6. Identity/auth/platform-core audit

### Verified platform identity model

Canonical user model:

- `UserAccount`
- `UserIdentity`
- `LocalCredentials`

Persistence model:

- `users`
- `user_identities`
- `local_credentials`

This is coherent across domain, application auth use cases, repositories, and migrations.

### Telegram as secondary identity

Telegram is now an external identity provider and adapter, not the canonical user shape.

Evidence:

- web registration/login works without Telegram
- external identity auth uses provider-based records
- reminder routing uses identity targets
- shared i18n is not Telegram-owned
- web adapter does not import Telegram adapter code

### Important nuance

Telegram is secondary in the core model, but not fully erased from compatibility surfaces:

- legacy Telegram columns remain in `users`
- reminder delivery currently targets Telegram identities only
- bot-first onboarding still creates users on first Telegram contact

This is compatible with the current architecture. It is not a contradiction. It is a deliberate compatibility posture.

### Typing consistency

Current state:

- workflow/facade use `UserAccount`
- `UserProfile` remains only as a compatibility alias in domain

This is acceptable but should remain temporary.

## 7. Persistence and migration audit

### Alignment status

Code alignment is good between:

- `app/adapters/postgres/models.py`
- `app/adapters/postgres/repositories.py`
- `alembic/versions/20260311_0002_platform_identity.py`

### Verified positive points

- `user_identities` schema matches ORM naming: `provider_user_id`, `provider_username`, `provider_display_name`
- `local_credentials` schema and auth use cases align
- reminder target queries use identities, not legacy user column
- workflow layer avoids direct persistence concerns

### Risks and under-tested areas

#### 1. Migration docs do not match actual schema names

`docs/migrations/identity-clean-break.md` documents:

- `external_user_id`
- `username`
- `display_name`
- `reminder_enabled`

Actual schema/migration use:

- `provider_user_id`
- `provider_username`
- `provider_display_name`
- no `reminder_enabled`

This is documentation drift, not code drift.

#### 2. Legacy Telegram column remains behaviorally active

Persistence layer still mirrors Telegram identity into `users.telegram_user_id`. This is a compatibility mechanism and should be documented as such.

#### 3. Migration/backfill testing could be stronger

Current tests give good confidence around current model behavior, but they do not deeply simulate upgrade/downgrade behavior across realistic legacy datasets with duplicates and mixed web/telegram states.

## 8. Documentation audit

### Accurate or mostly accurate

- `docs/DEVELOPMENT.md`: mostly accurate and aligned with runtime, auth routes, validation, and supported modes
- `docs/WEB_USER_CASES.md`: scenario content matches current web flows, but see encoding note below

### Stale

#### `docs/ARCHITECTURE.md`

The “Known Limitation” section still says workflow decomposition remains for a later wave and `HandleCommandUseCase` is still the central large orchestrator. That is outdated.

#### `docs/architecture/platform-core-refactor.md`

The “Remaining Gap” section still describes workflow decomposition as future work. That is outdated.

#### `docs/migrations/identity-clean-break.md`

Field names and one documented field do not match the actual schema and migration implementation. This is materially stale.

### Encoding / presentation issue

`docs/WEB_USER_CASES.md` and parts of `README.md` display mojibake when read in the current shell session, indicating an encoding/render mismatch. The scenario content still appears structurally valid, but the documentation presentation quality is degraded.

### Missing or understated documentation

- current workflow decomposition should be documented explicitly as completed, not pending
- the persistence compatibility seam around legacy Telegram columns should be documented as transitional
- “web-first” should be phrased more carefully to distinguish architecture from default configuration

## 9. Test and verification audit

### Validation run

Executed:

- `pytest -q` -> passed, `77 passed`
- `python -m compileall app tests` -> passed
- `docker compose config -q` -> passed

Also executed targeted suites successfully for workflow and adapter/boundary paths.

### What is well covered

- local registration/login
- external identity link/unlink
- unlink protection for last identity
- workflow decomposition modules
- interrupt flow
- web manual flow
- web bytes-based upload flow
- Telegram callback and renderer behavior
- architecture boundaries
- reminder deduplication via logs
- startup setting validation

### What confidence is justified

High confidence for:

- facade/wiring correctness
- workflow state transitions for main flows
- adapter independence at import boundary level
- current auth semantics

Moderate confidence for:

- migration upgrade/downgrade behavior on non-trivial legacy production-shaped data
- encoding/doc quality consistency across environments
- long-term prevention of `draft.py` growth

### High-value missing tests

1. migration-focused integration tests over legacy datasets with duplicate Telegram ids and mixed credential states
2. explicit tests for default/runtime mode expectations vs docs
3. explicit tests that repository legacy Telegram mirror behavior remains intentional and does not leak back into application assumptions
4. regression tests for hybrid runtime startup path if both adapters are enabled together with web Telegram auth

## 10. Residual technical debt

### Critical

None found that currently block safe continuation.

### Moderate

#### 1. Documentation drift around workflow completion

Why it matters:

- it misrepresents the current architecture
- future contributors may target already-solved problems instead of current hotspots

Suggested next step:

- update `docs/ARCHITECTURE.md`
- update `docs/architecture/platform-core-refactor.md`

#### 2. Migration doc/schema mismatch

Why it matters:

- migration docs are currently inaccurate at the field-contract level
- this can mislead operational work and manual verification

Suggested next step:

- correct `docs/migrations/identity-clean-break.md` to actual schema names and behavior

#### 3. Runtime defaults are not web-first

Why it matters:

- the repository markets itself as web-first, but `Settings` and `.env.example` default to `APP_ENABLE_TELEGRAM=true`, `APP_ENABLE_WEB=false`
- this creates an architecture/operations language mismatch

Suggested next step:

- either change defaults or document clearly that web-first is a recommended deployment mode, not the default local baseline

#### 4. Legacy Telegram persistence seam

Why it matters:

- legacy fields are still behaviorally maintained
- if left undocumented, they can reintroduce Telegram-centric assumptions

Suggested next step:

- document these fields as compatibility-only
- eventually remove them after migration confidence and deployment cutover allow it

### Low-priority

#### 1. `UserProfile` compatibility alias

Suggested next step:

- remove after import consumers fully stop referencing the old name

#### 2. `application/models.py` workflow re-export shim

Suggested next step:

- remove once imports are migrated to `app.application.workflow.models`

#### 3. `draft.py` concentration risk

Suggested next step:

- monitor size and split only when a clear new sub-scenario emerges

#### 4. Documentation encoding quality

Suggested next step:

- normalize README and web-user-case docs encoding/display path

## 11. Final verdict

### Is Telegram now a thin secondary adapter?

Mostly yes, with evidence. Telegram is no longer the canonical identity source or the owner of shared business logic. It remains a substantial adapter in UI/event handling, which is expected, but it is secondary at the core architecture level.

### Is the repository materially web-first?

Architecturally yes. Operationally by default config, not yet. Web can run independently and is supported by the identity/auth model, but defaults still start from Telegram-on/web-off.

### Is the architecture coherent?

Yes. The codebase now presents a coherent layered system with clear ownership of domain, application, workflow, presentation, adapter, and bootstrap responsibilities.

### Is workflow decomposition genuinely complete?

Yes for this phase. The previous workflow monolith has been meaningfully decomposed. The remaining risk is local growth inside `draft.py`, not failure of the decomposition itself.

### What should happen next?

1. Fix stale architecture and migration documentation.
2. Decide whether runtime defaults should match the web-first architectural claim.
3. Add migration-focused integration coverage for legacy upgrade paths.
4. Keep compatibility seams temporary and explicitly tracked.
