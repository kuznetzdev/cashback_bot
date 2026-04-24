# Пользовательские сценарии

Этот документ фиксирует текущие пользовательские flow на уровне общего application core и его delivery adapters.
Он описывает не vision, а фактически поддерживаемое поведение.

Продуктовое позиционирование и более широкий roadmap вынесены в [PRODUCT_OVERVIEW](C:\Users\Kuznetz\Desktop\proga\cashback_bot\docs\ru\PRODUCT_OVERVIEW.md).

## Назначение документа

- зафиксировать реальные точки входа в систему
- описать happy path и безопасные выходы
- показать ветки ошибок и interrupt-поведение
- убедиться, что web и Telegram используют один и тот же workflow core

## 1. Точки входа

### Web

- `GET /`
- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/logout`
- `GET /auth/telegram/callback`
- `POST /auth/telegram/unlink`
- `GET /app`
- `POST /app/action`
- `POST /app/input`
- `POST /app/upload`

### Telegram

- `/start`
- callbacks `nav:*`
- slash commands `/help`, `/home`, `/top`, `/settings`, `/banks`, `/cancel`
- текстовое сообщение
- фото-сообщение

## 2. Общие инварианты

- Любое пользовательское действие должно приводить к следующему экрану, статусу или локализованной ошибке.
- Silent state запрещен.
- Незавершенный draft нельзя молча потерять.
- Любой adapter обязан маппить входящие события в общий `UserCommand`.
- Любой adapter обязан рендерить общий `Screen`, а не собственную бизнес-логику.
- OCR и free-text parsing никогда не считаются финальным источником истины без preview.

## 3. First Value

### Цель

За короткий сценарий довести пользователя до первого полезного результата:

1. войти в продукт
2. создать или импортировать банк
3. проверить preview
4. сохранить банк
5. открыть детали банка или рейтинг

### Базовый happy path

1. Пользователь входит в систему.
2. Получает `home`.
3. Переходит в `add bank`.
4. Выбирает банк.
5. Выбирает способ ввода.
6. Формирует draft.
7. Проверяет и правит preview.
8. Сохраняет банк.
9. Переходит в `bank_details` или `top`.

## 4. Аутентификация и вход

### Flow: Local Web Auth

#### Регистрация

1. Пользователь открывает `/`.
2. Отправляет `POST /auth/register`.
3. Система создает platform user и `local_credentials`.
4. Создается web session.
5. Выполняется redirect на `/app`.

#### Вход

1. Пользователь открывает `/`.
2. Отправляет `POST /auth/login`.
3. Система проверяет local credentials.
4. Создается session.
5. Открывается `/app`.

### Flow: Telegram Identity Auth

#### Telegram bot

1. Пользователь пишет `/start`.
2. Telegram adapter строит `ExternalIdentityContext(provider="telegram")`.
3. Вызывается `authenticate_external_identity(... create_user_if_missing=True)`.
4. Пользователь попадает в общий workflow `start`.

#### Telegram callback в web

1. Пользователь проходит Telegram Login widget.
2. Web adapter принимает `/auth/telegram/callback`.
3. Если identity уже привязана, открывается существующий account.
4. Если callback идет из authenticated web session, identity может быть привязана к текущему пользователю.

### Guardrails

- Невалидная session не дает доступа к `/app`.
- Невалидный Telegram callback не должен создавать произвольный web session.
- Telegram identity не является канонической user-моделью, а только external identity provider.

## 5. Создание банка

### Flow: Add Bank -> Manual Input

1. `home -> open_add_bank`
2. выбор банка из preset или ввод имени
3. выбор метода `manual`
4. ввод строк вроде `АЗС 5%`
5. parser и normalization
6. переход в `preview`
7. редактирование
8. `save_bank`

Успешный выход:

- `bank_details`
- status effect о сохранении

Типовые ошибки:

- пустой текст
- нераспознаваемый формат строки
- некорректный процент

### Flow: Add Bank -> Photo OCR

1. `home -> open_add_bank`
2. выбор банка
3. выбор метода `photo`
4. переход в состояние `photo_upload`
5. adapter принимает изображение и строит `ImageUpload`
6. OCR use case извлекает текст
7. parser строит draft
8. открывается `preview`

Успешный выход:

- `bank_details` после `save_bank`

Типовые ошибки:

- файл больше разрешенного лимита
- битое изображение
- OCR timeout
- OCR не дал полезного результата

### Flow: Add Bank -> Template

1. `home -> open_add_bank`
2. выбор банка
3. выбор метода `template`
4. создание template-based draft
5. открытие `preview`
6. правка процентов и состава строк
7. `save_bank`

Правило:

- строки с `percent <= 0` не считаются валидными для сохранения

## 6. Preview и редактирование

`preview` — центральный рабочий экран текущего продукта.

Точки входа:

- после manual parse
- после OCR parse
- после template preload
- после `edit_bank`
- после `continue_draft`

Поддерживаемые действия:

- `pick_item`
- `add_item`
- `edit_item_category`
- `edit_item_percent`
- `delete_item`
- `open_preview`
- `save_bank`
- `cancel_flow`

Смысл flow:

- пока не вызван `save_bank`, изменения живут только в `WorkflowState`
- пользователь может свободно исправлять draft без записи в persistence

## 7. Сохранение draft

### Preconditions

- задан `selected_bank_name`
- draft не пустой
- все сохраняемые строки имеют валидный процент

### Поведение системы

1. Находит или создает банк пользователя.
2. При необходимости обновляет имя банка.
3. Атомарно заменяет набор `cashback_items`.
4. Добавляет запись в `user_logs`.
5. Возвращает `bank_details`.

### Результат

- банк сохранен как актуальный снимок текущих cashback-категорий
- пользователь видит сохраненное состояние, а не промежуточный draft

## 8. Работа с сохраненным банком

### Flow: Open Bank

1. `home -> open_my_banks`
2. пользователь выбирает банк
3. открывается `bank_details`

### Flow: Edit Saved Bank

1. `bank_details -> edit_bank`
2. система загружает `BankAggregate`
3. копирует текущие items в draft
4. пользователь повторно проходит `preview/edit`
5. `save_bank` заменяет сохраненное состояние

### Flow: Delete Bank

1. `bank_details -> request_delete_bank`
2. открывается экран подтверждения
3. пользователь подтверждает `confirm_delete_bank` или возвращается назад

Успешный выход:

- безопасный возврат на `home`

## 9. Рейтинг и быстрый выбор карты

### Flow: Open Top

1. `home -> open_top`
2. система загружает банки пользователя
3. строит ranking entries
4. рассчитывает лидеров по категориям
5. открывает `top`

### Flow: Open Top Category

1. пользователь выбирает категорию из `top`
2. открывается `top_category`
3. система показывает все лучшие варианты по этой категории

Правило:

- при ничьей сохраняются все лидеры, а не один произвольный банк

### Flow: Quick Query из свободного текста

Поддерживаемые варианты:

- запрос в духе "лучшая карта для азс"
- свободный текст, который parser понимает как best-category intent
- свободный текст, который parser понимает как delete intent

Поведение:

- text intent router пытается понять запрос
- при успехе переводит его в обычный workflow command
- при неуспехе возвращает help или понятный status effect

## 10. Настройки, история и напоминания

### Flow: Settings

1. `home -> open_settings`
2. пользователь меняет язык через `set_language`
3. пользователь включает или отключает напоминания через `toggle_notifications`

Результат:

- настройки сохраняются на уровне platform user

### Flow: History

1. `home -> open_history`
2. система читает `user_logs`
3. показывает последние действия пользователя

### Flow: Reminder Delivery

1. у пользователя включены уведомления
2. scheduler инициирует reminder use case
3. система находит linked reminder targets
4. sender adapter доставляет напоминание по доступному каналу

Текущее рабочее поведение:

- основная operational delivery-модель ориентирована на linked Telegram targets
- источник истины для маршрутизации — `user_identities`, а не legacy-поля на `users`

## 11. Interrupt flow

### Когда возникает interrupt

Interrupt нужен, когда пользователь пытается уйти с незавершенного draft flow на безопасную навигационную цель:

- `open_home`
- `open_top`
- `open_settings`
- `open_history`
- другие команды, которые уводят с текущего draft-сценария

### Поведение

Система вместо silent navigation открывает `interrupt_flow` и предлагает:

- `continue_draft`
- `discard_draft_and_go`
- `save_draft_and_go`, если draft уже валиден

### Отдельный случай

Interrupt может возникать даже если пользователь уже выбрал банк и метод ввода, но еще не собрал полноценный список cashback items.
Такое состояние тоже не должно теряться молча.

## 12. Telegram-specific особенности

Telegram adapter добавляет только transport-specific слой:

- `/start` и slash commands маппятся в обычные `UserCommand`
- inline кнопки кодируются как `nav:*`
- текст маппится либо в slash command, либо в `submit_text`
- фото принимаются только в `pending_input_kind == "photo_upload"`
- рендерер старается переиспользовать уже отправленный bot message и редактировать его на месте

Следствие:

- Telegram-бот уже не владеет workflow
- он является экранным и событийным адаптером поверх общего core

## 13. Ошибки и guardrails

Система должна корректно переживать:

- невалидный ввод пользователя
- ошибки OCR
- невалидные callbacks
- runtime и I/O ошибки adapter-уровня

Ожидаемое поведение:

- локализованная ошибка для пользователя
- сохранение валидного session/workflow state
- отсутствие silent failures

## 14. Что важно для дальнейшего развития

Любой новый flow должен сохранять текущие свойства:

- один общий `handle_command(...)` / workflow entrypoint semantics для всех adapters
- screen-driven navigation
- явный preview перед записью пользовательских данных
- interrupt protection для незавершенных draft-сценариев
- отсутствие transport-specific business logic внутри adapters
