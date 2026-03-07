# Web user cases

Краткая фиксация пользовательских сценариев для web adapter.

Источник логики:

- единое ядро `handle_command(...)`
- web только рендерит `Screen/Action`

## 1. Вход и session

### UC-WEB-001 Вход через Telegram Login

- предусловие: пользователь не авторизован
- шаги: открыть `/` -> пройти Telegram Login widget -> callback `/auth/telegram/callback`
- результат: пользователь синхронизирован в БД, открыт экран `home`

### UC-WEB-002 Протухшая или отсутствующая session

- шаги: открыть `/app` или отправить `/app/action` без валидной session
- результат: redirect на `/` без падения процесса

## 2. Добавление банка

### UC-WEB-010 Добавление через manual

- шаги: `home -> add_bank -> select_bank -> choose_input_method(manual) -> submit_manual_text -> preview -> save_bank`
- результат: банк сохранен атомарной заменой `cashback_items`, открыт `bank_details`

### UC-WEB-011 Добавление через photo (OCR)

- шаги: `home -> add_bank -> select_bank -> choose_input_method(photo) -> upload image -> preview -> save_bank`
- результат: OCR + parser + нормализация выполнены, данные сохранены

### UC-WEB-012 Добавление через template

- шаги: `home -> add_bank -> select_bank -> choose_input_method(template) -> preview -> edit -> save_bank`
- результат: draft создан из шаблона, нулевые проценты запрещены к сохранению

## 3. Редактирование и управление

### UC-WEB-020 Редактирование draft до сохранения

- шаги: на `preview` использовать `pick_item`, `edit category`, `edit percent`, `add item`, `delete item`
- результат: изменения применяются в draft state, экран `preview` остается консистентным

### UC-WEB-021 Редактирование сохраненного банка

- шаги: `my_banks -> bank_details -> edit_bank -> preview/edit -> save_bank`
- результат: текущий набор категорий банка полностью пересохраняется

### UC-WEB-022 Удаление банка

- шаги: `bank_details -> request_delete_bank -> confirm_delete_bank`
- результат: банк и категории удалены каскадно, пользователь возвращен в `home`

## 4. Аналитика, настройки, история

### UC-WEB-030 Рейтинг

- шаги: `home -> top -> top_category`
- результат: лучший процент по категориям, глобальный рейтинг банков, корректная обработка ничьих

### UC-WEB-031 Настройки

- шаги: `home -> settings -> set_language` и/или `toggle_notifications`
- результат: настройки сохранены в БД и сразу отражены в UI

### UC-WEB-032 История действий

- шаги: `home -> history`
- результат: показ последних записей `user_logs`

## 5. Прерывания и восстановление

### UC-WEB-040 Выход из незавершенного flow

- условие: есть активный draft или pending input
- шаги: пользователь пытается уйти на `home/top/settings/...`
- результат: экран `interrupt_flow` с явным выбором:
  - `continue_draft`
  - `discard_draft_and_go`
  - `save_draft_and_go` только если draft валиден

### UC-WEB-041 Прерывание во время ввода без items

- условие: выбран банк и метод ввода, но категории еще не внесены
- результат: тоже показывается `interrupt_flow`, silent drop состояния нет

## 6. Ошибки и защитные ветки

### UC-WEB-050 OCR ошибки

- кейсы: `file_too_large`, `broken_image`, `ocr_empty`, `ocr_timeout`
- результат: локализованное сообщение и сохранение валидного экрана

### UC-WEB-051 Невалидный ввод

- кейсы: невалидный процент, пустая категория, неизвестная команда
- результат: короткая ошибка, сценарий не ломается, есть путь продолжить или отменить

### UC-WEB-052 Missing сущности

- кейсы: несуществующий банк или категория при удалении или открытии
- результат: корректная domain error и безопасный экран

## 7. Навигационные инварианты

- любое действие возвращает следующий `Screen` или локализованный статус ошибки
- на каждом экране есть минимум один безопасный выход: `home`, `back` или `cancel`
- web не содержит бизнес-логики: только перевод HTTP input в `UserCommand` и рендер `Screen`
