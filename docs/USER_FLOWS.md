# User Flows

Этот документ фиксирует сквозные пользовательские сценарии продукта на уровне ядра и адаптеров.

Цель документа:

- описать все основные точки входа в систему
- описать ожидаемые выходы и безопасные пути завершения сценариев
- зафиксировать альтернативные ветки и ошибки
- не допустить "мертвых концов" в UX

Важно:

- документ описывает текущий baseline поведения системы
- если в продуктовой стратегии есть более широкий vision, но он еще не реализован, это фиксируется отдельно в [docs/PRODUCT_OVERVIEW.md](C:\Users\Kuznetz\Desktop\proga\cashback_bot\docs\PRODUCT_OVERVIEW.md)

## 1. Общая карта входов

### Web entry points

- `GET /`
  - вход для неавторизованного пользователя
  - показывает landing и Telegram Login
- `GET /auth/telegram/callback`
  - завершает авторизацию
  - синхронизирует пользователя
  - переводит в `home`
- `GET /app`
  - основной вход в приложение при активной сессии
  - восстанавливает последний `Screen` или открывает `home`
- `POST /app/action`
  - универсальная точка для action-based навигации
- `POST /app/input`
  - универсальная точка для текстового ввода
- `POST /app/upload`
  - точка приема изображения для OCR

### Telegram entry points

- `/start`
  - регистрация или синхронизация пользователя
  - открытие `home`
- callbacks `nav:*`
  - основной канал навигации по inline-экранам
- slash commands
  - `/help`
  - `/home`
  - `/top`
  - `/settings`
  - `/banks`
  - `/cancel`
- text message
  - свободный текст
  - ручной ввод по текущему flow
  - NL-query "чем платить"
  - NL-delete intents
- photo message
  - OCR flow, если текущее состояние ждет фото

## 2. Общие UX-инварианты

- Любой пользовательский ввод должен привести к одному из результатов:
  - следующий экран
  - status message
  - error message
- Silent state запрещен.
- На каждом экране должен быть хотя бы один безопасный выход:
  - `open_home`
  - `open_preview`
  - `cancel_flow`
  - `open_bank`
  - `open_top`
- При попытке выйти из незавершенного сценария пользователь должен попасть в `interrupt_flow`, а не терять данные молча.
- Web и Telegram обязаны проходить через одну и ту же семантику `handle_command(...)`.

## 3. Основной сценарий: First Value

### Цель

За 1-2 минуты довести пользователя до первого полезного результата:

- добавить данные по карте
- проверить распознавание
- получить рейтинг или детальную карточку банка

### Базовый happy path

1. Пользователь входит в продукт.
2. Открывается `home`.
3. Пользователь идет в `add bank`.
4. Выбирает банк или вводит свой alias.
5. Выбирает способ ввода.
6. Загружает данные.
7. Проверяет preview.
8. Сохраняет.
9. Переходит в `bank_details` или `top`.

### Возможные выходы

- завершить сохранением
- отменить и вернуться в `home`
- перейти на другой экран через `interrupt_flow`

## 4. Flow: Add Bank -> Manual Input

### Входы

- `home -> open_add_bank`

### Предусловия

- пользователь авторизован и синхронизирован

### Шаги

1. Открывается `choose_bank`.
2. Пользователь:
   - выбирает preset-банк
   - или идет в `select_bank_other`
3. Если выбран "other":
   - открывается `custom_bank_name`
   - ожидается `custom_bank_name` input
4. После выбора имени банка открывается `input_method`.
5. Пользователь выбирает `manual`.
6. Открывается `manual_prompt`.
7. Пользователь отправляет строки вида:
   - `АЗС 5%`
   - `Restaurants - 7.5%`
   - `Movies 10`
8. Ядро:
   - парсит строки
   - нормализует категории
   - формирует `draft_items`
9. Открывается `preview`.
10. Пользователь:
   - редактирует
   - или сохраняет

### Успешный выход

- `save_bank -> bank_details`

### Альтернативные выходы

- `cancel_flow -> home`
- `open_home/open_top/open_settings/... -> interrupt_flow`

### Ошибки

- пустой текст
- невалидный формат строки
- невалидный процент

### Ожидаемое поведение при ошибке

- показать короткую ошибку
- сохранить валидный экран
- не сбрасывать пользователя в пустоту

## 5. Flow: Add Bank -> Photo OCR

### Входы

- `home -> open_add_bank`

### Шаги

1. Пользователь выбирает банк.
2. На `input_method` выбирает `photo`.
3. Открывается `photo_prompt`.
4. Пользователь загружает изображение.
5. OCR adapter:
   - валидирует размер файла
   - сохраняет временный файл
   - выполняет preprocessing
   - запускает `pytesseract` вне event loop
   - возвращает текст
6. Ядро:
   - парсит OCR text
   - нормализует категории
   - формирует draft
7. Открывается `preview`.

### Успешный выход

- `save_bank -> bank_details`

### Альтернативные выходы

- `open_preview` после редактирования
- `cancel_flow -> home`
- прерывание сценария через `interrupt_flow`

### Ошибки

- файл слишком большой
- битое изображение
- OCR timeout
- OCR не распознал полезный текст

### Ожидаемое поведение

- показать локализованную ошибку
- для `ocr_empty` добавить пользовательскую подсказку
- оставить пользователя на валидном экране

## 6. Flow: Add Bank -> Template

### Шаги

1. Пользователь выбирает банк.
2. На `input_method` выбирает `template`.
3. Система создает `draft_items` из шаблонных категорий.
4. Открывается `preview`.
5. Пользователь задает проценты и редактирует состав строк.

### Особое правило

- строки с `percent <= 0` нельзя сохранять

### Успешный выход

- `save_bank -> bank_details`

### Альтернативные выходы

- `cancel_flow -> home`
- прерывание через `interrupt_flow`

## 7. Flow: Preview Editing

`preview` — центральный рабочий экран редактирования.

### Доступные входы

- после manual parse
- после OCR parse
- после template preload
- после `edit_bank`
- после `continue_draft`
- после возврата из `edit_item`

### Доступные действия

- `pick_item`
- `add_item`
- `save_bank`
- `cancel_flow`

### Поведение `pick_item`

- открывает `edit_item`
- пользователь выбирает:
  - `edit_item_category`
  - `edit_item_percent`
  - `delete_item`
  - `open_preview`

### Поведение `add_item`

1. `add_item -> item_category_prompt`
2. пользователь вводит категорию
3. `item_percent_prompt`
4. пользователь вводит процент
5. возврат в `preview`

### Возможные выходы

- `save_bank`
- `cancel_flow`
- `interrupt_flow`

## 8. Flow: Save Draft

### Preconditions для сохранения

- задан `selected_bank_name`
- draft не пустой
- у всех items `percent > 0`

### Действия системы

- находит или создает банк
- при необходимости обновляет имя
- атомарно заменяет набор `cashback_items`
- пишет `user_logs`

### Успешный выход

- открывается `bank_details`
- показывается transient status `saved_bank`

### Ошибки

- не задан банк
- нет items
- есть нулевые проценты
- ошибка транзакции / БД

## 9. Flow: Edit Saved Bank

### Входы

- `home -> open_my_banks -> open_bank -> edit_bank`

### Шаги

1. Загружается текущий `BankAggregate`.
2. Его items клонируются в `WorkflowState.draft_items`.
3. Пользователь попадает в тот же `preview`, что и в add-flow.
4. Дальше работает тот же набор действий:
   - edit
   - add
   - delete
   - save

### Успешный выход

- `save_bank -> bank_details`

### Ошибки

- банк не найден

## 10. Flow: Delete Bank

### Входы

- `bank_details -> request_delete_bank`

### Шаги

1. Открывается `confirm_delete_bank`.
2. Пользователь:
   - подтверждает удаление
   - или возвращается в `bank_details`

### Успешный выход

- `confirm_delete_bank -> home`
- показывается сообщение об удалении

### Ошибки

- банк не найден к моменту удаления

## 11. Flow: Ranking

### Входы

- `home -> open_top`
- свободный текст best-query

### Шаги

1. Загружаются все банки пользователя.
2. Собираются ranking entries.
3. Считаются:
   - лидеры по каждой категории
   - глобальный рейтинг банков
4. Открывается `top`.
5. Пользователь может открыть конкретную категорию через `open_top_category`.

### Успешные выходы

- `top`
- `top_category`

### Особые правила

- при ничьей все лидеры категории сохраняются
- в глобальном рейтинге баллы получают все лидеры категории

### Ошибки / empty states

- если данных нет, показывается `no_ranking_data`

## 12. Flow: Quick Query / "Чем платить?"

### Входы

- Telegram text
- Web text input, когда пользователь вводит запрос, а не структурированные данные

### Поддерживаемые intent types

- best query
  - `лучший кэшбэк на азс`
  - `где лучше рестораны`
  - `best cashback for fuel`
- delete query
  - `удали банк X`
  - `удали категорию Y`

### Поведение best-query

1. parser пытается извлечь intent
2. category service нормализует запрос
3. ядро открывает `top_category`

### Поведение delete-bank query

1. parser извлекает intent
2. система ищет близкое имя банка
3. удаляет банк
4. возвращает пользователя в `home`

### Поведение delete-category query

1. parser извлекает intent
2. category service расширяет целевые slug'и
3. система удаляет category items по всем банкам пользователя
4. открывается `delete_category_result`

### Если intent не распознан

- открывается `help`
- показывается status/error по unknown command

## 13. Flow: Settings

### Входы

- `home -> open_settings`

### Действия

- `set_language(ru|en)`
- `toggle_notifications`

### Выход

- повторный рендер `settings` с актуальным состоянием

### Ошибки

- невалидный код языка
- пользователь не найден

## 14. Flow: History

### Входы

- `home -> open_history`

### Поведение

- загружает последние записи из `user_logs`
- показывает empty state, если логов нет

### Выход

- `history`
- возврат в `home`

## 15. Flow: Interrupt And Recovery

Это один из наиболее важных защитных сценариев.

### Когда срабатывает

Если у пользователя есть активный незавершенный flow:

- есть draft items
- или выбран банк
- или есть pending input
- или идет добавление/редактирование item

И пользователь пытается уйти на:

- `open_home`
- `open_help`
- `open_add_bank`
- `open_my_banks`
- `open_top`
- `open_settings`
- `open_history`
- `cancel_flow`
- `start`

### Тогда открывается `interrupt_flow`

Пользователь видит варианты:

- `continue_draft`
- `discard_draft_and_go`
- `save_draft_and_go` если draft валиден

### Ветки выхода

#### Continue

- возврат в `preview`

#### Discard

- state очищается
- выполняется целевое действие
- показывается `draft_discarded`

#### Save And Go

- draft сохраняется
- state очищается
- выполняется целевое действие
- показывается `saved_bank`

## 16. Web Session Flow

### Вход при валидной сессии

- `GET /app` рендерит текущий экран

### Вход без сессии

- redirect на `/`

### Logout

- `POST /auth/logout`
- очистка session
- redirect на landing

### Session-backed state

В web session хранятся:

- user profile snapshot
- workflow state
- cached screen

Если screen cache отсутствует:

- система открывает `home`

## 17. Telegram-Specific Flow Notes

### Slash commands

- `/help -> open_help`
- `/home -> open_home`
- `/top -> open_top`
- `/settings -> open_settings`
- `/banks -> open_my_banks`
- `/cancel -> cancel_flow`

### Photo message

- если `pending_input_kind != photo_upload`, пользователь получает `send_photo_or_text`
- иначе запускается OCR flow

### Callback behavior

- если callback decode не удался, пользователь получает ошибку
- callback query закрывается best-effort

## 18. Карта экранов и переходов

Ниже перечислены screen ids текущего baseline и их ключевые входы/выходы.

### `home`

Входы:

- `/start`
- `open_home`
- после logout/login на web
- после успешного удаления банка
- после `discard_draft_and_go` в home

Выходы:

- `open_add_bank`
- `open_my_banks`
- `open_top`
- `open_settings`
- `open_history`
- `open_help`

### `help`

Входы:

- `open_help`
- unknown free text fallback

Выходы:

- `open_home`

### `choose_bank`

Входы:

- `open_add_bank`

Выходы:

- `select_bank_preset`
- `select_bank_other`
- `open_home`

### `custom_bank_name`

Входы:

- `select_bank_other`

Выходы:

- submit text -> `submit_custom_bank_name`
- `cancel_flow`

### `input_method`

Входы:

- после выбора банка

Выходы:

- `choose_input_method(manual|photo|template)`
- `cancel_flow`

### `manual_prompt`

Входы:

- `choose_input_method(manual)`

Выходы:

- submit text
- `cancel_flow`

### `photo_prompt`

Входы:

- `choose_input_method(photo)`

Выходы:

- upload photo
- `cancel_flow`

### `preview`

Входы:

- после manual/photo/template
- после `continue_draft`
- после item edit/add
- после `edit_bank`

Выходы:

- `pick_item`
- `add_item`
- `save_bank`
- `cancel_flow`

### `edit_item`

Входы:

- `pick_item`

Выходы:

- `edit_item_category`
- `edit_item_percent`
- `delete_item`
- `open_preview`

### `item_category_prompt`

Входы:

- `add_item`
- `edit_item_category`

Выходы:

- submit text
- `open_preview`

### `item_percent_prompt`

Входы:

- после category prompt
- `edit_item_percent`

Выходы:

- submit text
- `open_preview`

### `my_banks`

Входы:

- `open_my_banks`
- после `save_draft_and_go` с target `open_my_banks`

Выходы:

- `open_bank`
- `open_home`

### `bank_details`

Входы:

- `open_bank`
- после `save_bank`

Выходы:

- `edit_bank`
- `request_delete_bank`
- `open_home`

### `confirm_delete_bank`

Входы:

- `request_delete_bank`

Выходы:

- `confirm_delete_bank`
- `open_bank`

### `top`

Входы:

- `open_top`
- после `save_draft_and_go` с target `open_top`

Выходы:

- `open_top_category`
- `open_home`

### `top_category`

Входы:

- `open_top_category`
- best-query intent

Выходы:

- `open_top`
- `open_home`

### `settings`

Входы:

- `open_settings`
- после `save_draft_and_go` с target `open_settings`

Выходы:

- `set_language`
- `toggle_notifications`
- `open_home`

### `history`

Входы:

- `open_history`
- после `save_draft_and_go` с target `open_history`

Выходы:

- `open_home`

### `interrupt_flow`

Входы:

- любая попытка выйти из активного draft-flow

Выходы:

- `continue_draft`
- `discard_draft_and_go`
- `save_draft_and_go`

### `delete_category_result`

Входы:

- delete-category text intent

Выходы:

- `open_home`
