# Пользовательские сценарии

Этот документ фиксирует сквозные пользовательские сценарии продукта на уровне ядра и адаптеров.

Цель документа:

- описать основные точки входа в систему
- описать ожидаемые выходы и безопасные пути завершения сценариев
- зафиксировать альтернативные ветки и ошибки
- не допустить dead ends в UX

Важно:

- документ описывает текущий baseline поведения системы
- более широкий vision фиксируется отдельно в [docs/ru/PRODUCT_OVERVIEW.md](C:\Users\Kuznetz\Desktop\proga\cashback_bot\docs\ru\PRODUCT_OVERVIEW.md)

## 1. Общая карта входов

### Web entry points

- `GET /`
- `GET /auth/telegram/callback`
- `GET /app`
- `POST /app/action`
- `POST /app/input`
- `POST /app/upload`

### Telegram entry points

- `/start`
- callbacks `nav:*`
- slash commands `/help`, `/home`, `/top`, `/settings`, `/banks`, `/cancel`
- text message
- photo message

## 2. Общие UX-инварианты

- Любой пользовательский ввод должен приводить к следующему экрану, status message или error message.
- Silent state запрещен.
- На каждом экране должен быть безопасный выход.
- При попытке выйти из незавершенного сценария пользователь должен попадать в `interrupt_flow`.
- Web и Telegram обязаны использовать одну и ту же семантику `handle_command(...)`.

## 3. Основной сценарий: First Value

### Цель

За 1-2 минуты довести пользователя до первого полезного результата:

- добавить данные по банку/карте
- проверить распознавание
- получить рейтинг или карточку банка

### Базовый happy path

1. Пользователь входит в продукт.
2. Открывается `home`.
3. Пользователь идет в `add bank`.
4. Выбирает банк или вводит alias.
5. Выбирает способ ввода.
6. Загружает данные.
7. Проверяет preview.
8. Сохраняет.
9. Переходит в `bank_details` или `top`.

## 4. Flow: Add Bank -> Manual Input

- вход: `home -> open_add_bank`
- выбор банка: preset или custom name
- выбор метода: `manual`
- ввод строк вида `АЗС 5%`
- parser + normalization
- переход в `preview`
- редактирование и сохранение

Выходы:

- `save_bank -> bank_details`
- `cancel_flow -> home`
- `interrupt_flow` при попытке уйти

Ошибки:

- пустой текст
- невалидный формат
- невалидный процент

## 5. Flow: Add Bank -> Photo OCR

- вход: `home -> open_add_bank`
- выбор банка
- выбор метода `photo`
- загрузка изображения
- OCR adapter: validation, temp file, preprocessing, tesseract, cleanup
- parser + normalization
- переход в `preview`

Выходы:

- `save_bank -> bank_details`
- `cancel_flow -> home`
- `interrupt_flow`

Ошибки:

- слишком большой файл
- битое изображение
- OCR timeout
- OCR не дал полезный текст

## 6. Flow: Add Bank -> Template

- выбор банка
- выбор метода `template`
- создание template draft
- открытие `preview`
- заполнение процентов и правка состава строк

Особое правило:

- строки с `percent <= 0` нельзя сохранять

## 7. Flow: Preview Editing

`preview` — главный экран редактирования.

Входы:

- после manual parse
- после OCR parse
- после template preload
- после `edit_bank`
- после `continue_draft`

Действия:

- `pick_item`
- `add_item`
- `save_bank`
- `cancel_flow`

Внутри item editing:

- `edit_item_category`
- `edit_item_percent`
- `delete_item`
- `open_preview`

## 8. Flow: Save Draft

Preconditions:

- задан `selected_bank_name`
- draft не пустой
- все items имеют `percent > 0`

Система:

- создает или находит банк
- обновляет имя при необходимости
- атомарно заменяет `cashback_items`
- пишет `user_logs`

Успешный выход:

- `bank_details`
- status `saved_bank`

## 9. Flow: Edit Saved Bank

Вход:

- `home -> open_my_banks -> open_bank -> edit_bank`

Шаги:

- загрузка `BankAggregate`
- клонирование items в draft
- повторное использование `preview`
- сохранение целиком

## 10. Flow: Delete Bank

Вход:

- `bank_details -> request_delete_bank`

Шаги:

- `confirm_delete_bank`
- подтверждение или возврат назад

Успешный выход:

- `home`

## 11. Flow: Ranking

Вход:

- `home -> open_top`
- best-query из свободного текста

Шаги:

- загрузка банков пользователя
- сбор ranking entries
- расчет category leaders
- расчет top global
- открытие `top`
- переход в `top_category`

Особое правило:

- при ничьей сохраняются все лидеры

## 12. Flow: Quick Query / «Чем платить?»

Поддерживаемые intent types:

- best query
- delete bank
- delete category

Best-query открывает `top_category`.
Delete-bank удаляет банк и возвращает в `home`.
Delete-category открывает `delete_category_result`.
Если intent не распознан, открывается `help`.

## 13. Flow: Settings

Вход:

- `home -> open_settings`

Действия:

- `set_language(ru|en)`
- `toggle_notifications`

Выход:

- повторный рендер `settings`

## 14. Flow: History

Вход:

- `home -> open_history`

Поведение:

- загрузка последних `user_logs`
- empty state, если логов нет

## 15. Flow: Interrupt And Recovery

Срабатывает, если у пользователя есть активный незавершенный flow:

- есть draft items
- выбран банк
- есть pending input
- идет редактирование item

При попытке уйти на другой раздел открывается `interrupt_flow`.

Варианты:

- `continue_draft`
- `discard_draft_and_go`
- `save_draft_and_go`, если draft валиден

## 16. Web session flow

- `GET /app` при валидной session рендерит текущий экран
- без session делает redirect на `/`
- `POST /auth/logout` очищает session и ведет на landing

## 17. Telegram-specific notes

- slash commands маппятся в `UserCommand`
- photo message работает только при `pending_input_kind == photo_upload`
- callback errors отдаются пользователю без падения процесса

## 18. Карта экранов

Базовые screen ids текущего baseline:

- `home`
- `help`
- `choose_bank`
- `custom_bank_name`
- `input_method`
- `manual_prompt`
- `photo_prompt`
- `preview`
- `edit_item`
- `item_category_prompt`
- `item_percent_prompt`
- `my_banks`
- `bank_details`
- `confirm_delete_bank`
- `top`
- `top_category`
- `settings`
- `history`
- `interrupt_flow`
- `delete_category_result`
