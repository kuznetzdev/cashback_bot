# Cashback Analyzer Web: User Cases

This document captures the main user scenarios for the web adapter.
Business logic remains shared: the application returns `Screen` and accepts `UserCommand`, while the web adapter only maps HTTP/session events and renders the result.

## 1. Authentication

### UC-WEB-001 Local registration

- Precondition: user is not authenticated.
- Steps: open `/`, fill registration form, submit `POST /auth/register`.
- Result: platform user is created, local credentials are created, session is opened, redirect to `/app`.

### UC-WEB-002 Local login

- Precondition: user already has local credentials.
- Steps: open `/`, fill login form, submit `POST /auth/login`.
- Result: session is created, `/app` is opened.

### UC-WEB-003 Telegram callback login for an already linked identity

- Precondition: Telegram identity is already linked to a platform user.
- Steps: open `/auth/telegram/callback` through Telegram Login widget.
- Result: user is authenticated into the existing account.

### UC-WEB-004 Link Telegram to an already authenticated web user

- Precondition: user is already logged in locally.
- Steps: open `/app`, start Telegram linking flow, finish callback.
- Result: `user_identities` receives `provider=telegram` for the current platform user, current web session is preserved.

### UC-WEB-005 Unlink Telegram

- Precondition: Telegram identity is linked.
- Steps: `POST /auth/telegram/unlink`.
- Result: Telegram identity is removed, local auth remains available.

### UC-WEB-006 Unauthenticated access to the application

- Steps: open `/app` or send POST to `/app/action` without a valid session.
- Result: redirect to `/`.

## 2. Bank creation

### UC-WEB-010 Add bank manually

- Steps: `home -> add_bank -> select_bank -> choose_input_method(manual) -> submit_manual_text -> preview -> save_bank`.
- Result: bank and cashback items are stored transactionally.

### UC-WEB-011 Add bank from image

- Steps: `home -> upload image -> OCR -> attach_bank/select_existing_bank -> preview -> set_target_month -> save_bank`.
- Result: web adapter sends `ImageUpload`, OCR and parser build the draft, then the user attaches parsed categories to a bank and month before saving.

### UC-WEB-011A Add bank from image when exactly one saved bank exists

- Precondition: user already has exactly one saved bank.
- Steps: `home -> upload image -> OCR`.
- Result: workflow auto-selects the only bank, opens preview immediately, and removes one extra decision step from the flow.

### UC-WEB-012 Add bank from template

- Steps: `home -> add_bank -> select_bank -> choose_input_method(template) -> preview/edit -> save_bank`.
- Result: a draft is created from template items, then edited and saved like a regular bank draft.

## 3. Editing

### UC-WEB-020 Edit draft

- Steps: on preview use `pick_item`, edit category, edit percent, add item, delete item.
- Result: changes apply only to `WorkflowState` until `save_bank` is triggered.

### UC-WEB-021 Edit saved bank

- Steps: `my_banks -> bank_details(month) -> edit_bank -> preview/edit -> save_bank`.
- Result: the saved set of bank categories is replaced only for the selected month snapshot.

### UC-WEB-023 Save categories for a different month

- Steps: open preview, use `set_target_month(previous/current/next)`, then `save_bank`.
- Result: cashback items are stored for the selected month without overwriting another month.

### UC-WEB-022 Delete bank

- Steps: `bank_details -> request_delete_bank -> confirm_delete_bank`.
- Result: bank and its cashback items are removed, user returns to a safe screen.

## 4. Analytics and settings

### UC-WEB-030 View ranking

- Steps: `home -> top -> top_category`.
- Result: best cashback by category and global bank ranking are shown.

### UC-WEB-031 Profile settings

- Steps: `home -> settings -> set_language` and/or `toggle_notifications`.
- Result: settings are persisted on the platform user.

### UC-WEB-032 Action history

- Steps: `home -> history`.
- Result: recent entries from `user_logs` are shown.

## 5. Interrupt flow

### UC-WEB-040 Interrupt an unfinished draft flow

- Precondition: user has a draft or pending input.
- Steps: user tries to go to `home`, `top`, `settings`, `history`, or another safe navigation target.
- Result: `interrupt_flow` screen is shown with:
  - `continue_draft`
  - `discard_draft_and_go`
  - `save_draft_and_go` if the draft is valid for saving

### UC-WEB-041 Interrupt while selecting bank or input method

- Precondition: bank is already selected, but cashback items are not saved yet.
- Steps: user leaves the current flow.
- Result: state is not lost silently; interrupt screen is shown.

## 6. Errors and guardrails

### UC-WEB-050 OCR errors

- Cases: file too large, broken image, empty OCR result, timeout.
- Result: localized error is shown, user remains in a valid state.

### UC-WEB-053 Stale processing overlay recovery

- Case: user returns to the tab after upload or navigation resumes from browser cache.
- Result: loading overlay is cleared on `load`, `pageshow`, visible-tab restore, and timeout fallback.

### UC-WEB-051 Invalid input

- Cases: invalid percent, empty category, invalid login data, taken username.
- Result: user receives a clear error without losing valid session or draft state.

### UC-WEB-052 Invalid Telegram callback

- Cases: unsigned callback, callback for missing or unlinked identity.
- Result: access is denied and user returns to landing/login flow.

## 7. Navigation invariants

- Web does not contain business logic for ranking, OCR, bank persistence, or identity rules.
- Every step returns either the next `Screen` or a localized error.
- Each screen has a safe path back or home.
- Session stores only platform `user_id` and workflow/session state, not a Telegram-centric identity model.
