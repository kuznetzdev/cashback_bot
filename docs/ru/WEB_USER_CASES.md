# Cashback Analyzer Web: User Cases

Этот документ фиксирует основные пользовательские сценарии web adapter.
Бизнес-логика остается общей: application возвращает `Screen` и принимает `UserCommand`, а web adapter только маппит HTTP/session events и рендерит результат.

## 1. Аутентификация

### UC-WEB-001 Локальная регистрация

- Предусловие: пользователь не аутентифицирован.
- Шаги: открыть `/`, заполнить форму регистрации, отправить `POST /auth/register`.
- Результат: создается platform user, создаются local credentials, открывается session, выполняется redirect на `/app`.

### UC-WEB-002 Локальный вход

- Предусловие: у пользователя уже есть local credentials.
- Шаги: открыть `/`, заполнить форму входа, отправить `POST /auth/login`.
- Результат: создается session, открывается `/app`.

### UC-WEB-003 Вход через Telegram callback для уже привязанной identity

- Предусловие: Telegram identity уже привязана к platform user.
- Шаги: открыть `/auth/telegram/callback` через Telegram Login widget.
- Результат: пользователь аутентифицируется в существующий account.

### UC-WEB-004 Привязка Telegram к уже аутентифицированному web user

- Предусловие: пользователь уже вошел локально.
- Шаги: открыть `/app`, начать Telegram linking flow, завершить callback.
- Результат: в `user_identities` появляется `provider=telegram` для текущего platform user, текущая web session сохраняется.

### UC-WEB-005 Отвязка Telegram

- Предусловие: Telegram identity привязана.
- Шаги: `POST /auth/telegram/unlink`.
- Результат: Telegram identity удаляется, local auth остается доступным.

### UC-WEB-006 Неаутентифицированный доступ к приложению

- Шаги: открыть `/app` или отправить POST в `/app/action` без валидной session.
- Результат: redirect на `/`.

## 2. Создание банка

### UC-WEB-010 Добавление банка вручную

- Шаги: `home -> add_bank -> select_bank -> choose_input_method(manual) -> submit_manual_text -> preview -> save_bank`.
- Результат: банк и cashback items сохраняются транзакционно.

### UC-WEB-011 Добавление банка по изображению

- Шаги: `home -> add_bank -> select_bank -> choose_input_method(photo) -> upload image -> preview -> save_bank`.
- Результат: web adapter передает `ImageUpload`, OCR и parser строят draft, пользователь подтверждает и сохраняет его.

### UC-WEB-012 Добавление банка из шаблона

- Шаги: `home -> add_bank -> select_bank -> choose_input_method(template) -> preview/edit -> save_bank`.
- Результат: создается draft из template items, затем редактируется и сохраняется как обычный bank draft.

## 3. Редактирование

### UC-WEB-020 Редактирование draft

- Шаги: на preview использовать `pick_item`, edit category, edit percent, add item, delete item.
- Результат: изменения применяются только к `WorkflowState`, пока не вызван `save_bank`.

### UC-WEB-021 Редактирование сохраненного банка

- Шаги: `my_banks -> bank_details -> edit_bank -> preview/edit -> save_bank`.
- Результат: сохраненный набор категорий банка полностью заменяется новым draft.

### UC-WEB-022 Удаление банка

- Шаги: `bank_details -> request_delete_bank -> confirm_delete_bank`.
- Результат: банк и его cashback items удаляются, пользователь возвращается на безопасный экран.

## 4. Аналитика и настройки

### UC-WEB-030 Просмотр рейтинга

- Шаги: `home -> top -> top_category`.
- Результат: показываются лучшие cashback по категориям и глобальный рейтинг банков.

### UC-WEB-031 Настройки профиля

- Шаги: `home -> settings -> set_language` и/или `toggle_notifications`.
- Результат: настройки сохраняются на уровне platform user.

### UC-WEB-032 История действий

- Шаги: `home -> history`.
- Результат: отображаются последние записи из `user_logs`.

## 5. Interrupt flow

### UC-WEB-040 Прерывание незавершенного draft flow

- Предусловие: у пользователя есть draft или pending input.
- Шаги: пользователь пытается уйти на `home`, `top`, `settings`, `history` или другой safe navigation target.
- Результат: показывается `interrupt_flow` с выбором:
  - `continue_draft`
  - `discard_draft_and_go`
  - `save_draft_and_go`, если draft уже валиден для сохранения

### UC-WEB-041 Прерывание на этапе выбора банка или метода ввода

- Предусловие: банк уже выбран, но cashback items еще не сохранены.
- Шаги: пользователь покидает текущий flow.
- Результат: состояние не теряется молча, показывается interrupt screen.

## 6. Ошибки и guardrails

### UC-WEB-050 OCR ошибки

- Кейсы: слишком большой файл, битое изображение, пустой OCR result, timeout.
- Результат: показывается локализованная ошибка, пользователь остается в валидном состоянии.

### UC-WEB-051 Невалидный ввод

- Кейсы: невалидный процент, пустая категория, невалидные login data, занятое имя пользователя.
- Результат: пользователь получает понятную ошибку без потери валидной session или draft state.

### UC-WEB-052 Невалидный Telegram callback

- Кейсы: неподписанный callback, callback для отсутствующей или не привязанной identity.
- Результат: доступ не предоставляется, пользователь возвращается в landing/login flow.

## 7. Navigation invariants

- Web не содержит business logic для ranking, OCR, bank persistence или identity rules.
- Каждый шаг возвращает либо следующий `Screen`, либо локализованную ошибку.
- На каждом экране есть безопасный путь назад или домой.
- Session хранит только platform `user_id` и workflow/session state, а не telegram-centric identity model.
