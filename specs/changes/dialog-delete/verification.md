# Verification: удаление истории из «Мои истории»

Спецификация: [spec.md](./spec.md), план: [plan.md](./plan.md).
Дата проверки: 2026-10-18, ветка `feat/user-dialog-history`.

## Команды

| Команда | Результат |
| --- | --- |
| `make test` | frontend: 143 passed; backend: 339 passed, 27 skipped (тесты PostgreSQL/Redis без `TEST_*_URL`) |
| `TEST_DATABASE_URL=… pytest backend/tests/integration/db` на временном `postgres:17-alpine` | 24 passed |
| `make lint` | 96 файлов отформатированы, `All checks passed!` |

## Порядок TDD и отклонения

**Тесты, которые падали до реализации:**

- хранилище и сервис — 4 теста;
- API — до добавления маршрута тест завис: без `DELETE` диалог не удалялся,
  и `GET …/events` открывал бесконечный SSE-поток; тест остановлен, маршрут
  добавлен;
- клиент API — 2 теста;
- UI — 8 тестов.

**Отклонения:**

- Реализацию `PostgresHistoryStore.delete` я написала в задаче 1 вместе с
  хранилищем в памяти, до своего интеграционного теста (задача 3). Поэтому
  тест PostgreSQL прошёл сразу, без шага RED.
- В реализации списка я по ошибке вставила `return` в середину
  `renderHistory`. Три существующих теста списка упали, ошибка исправлена.
- В CSS общее правило `:disabled` (`opacity:.55`) проявило бы скрытые
  корзины, пока агент отвечает. Это замечено при ревью и исправлено
  отдельным правилом. Автотест для CSS в fake DOM невозможен.
- При ручной проверке на компьютере текст «Удалить историю?» обрезался до
  «Удали…» в панели шириной 280px. Подтверждение переделано в две строки.

## Ручная проверка

Проверка через CDP настоящими событиями мыши и клавиатуры на
`127.0.0.1:8081`, пользователь `sdd_krosh`. Удалялись мусорные истории,
которые я создала при прошлых проверках.

**Компьютер 1280px:**

- Корзина видна только у строки под курсором (`opacity` 0/1).
- Клик по корзине — строка «Удалить историю?», «Удалить», «Отмена»; фокус
  на «Отмена».
- `Escape` — строка вернулась, фокус на корзине.
- «Удалить» — «Проверка длины» исчезла из списка, открытая «Новая история»
  осталась.
- Открыта «Одной фразой: Крош и Ёжик пьют чай» и удалена — в чате новая
  история с Крошем.
- Сервер:
  - `GET /api/v1/dialogs` без удалённых историй;
  - `GET …/messages` удалённой истории — `404`;
  - в журнале два `dialog.deleted` только с `dialog_id`.

**Телефон 390px:**

- Корзины видны у всех историй (`opacity` 1).
- Подтверждение в две строки помещается в панель.
- Удаление работает.
- `scrollWidth` 390.

Скриншоты лежат в `~/Desktop/макеты-смешарики/удаление/`.

## Требования

| Требование | Проверка | Результат |
| --- | --- | --- |
| REQ-001 | `test_deleted_dialog_is_gone_from_every_route` (`204`); `test_delete_removes_dialog_messages_and_ratings` (каскад в PostgreSQL) | Выполнено |
| REQ-002 | `test_foreign_or_missing_dialog_is_not_found_and_kept`, `test_bad_id_is_422_and_guest_gets_401_first`, `test_unavailable_store_returns_503` | Выполнено |
| REQ-003 | `test_deleted_dialog_is_gone_from_every_route` (список, история, отправка, события, оценка, повторное удаление) | Выполнено |
| REQ-004 | `test_answer_for_a_deleted_dialog_is_dropped_with_an_error` | Выполнено |
| REQ-005 | `test_delete_dialog_removes_it_and_logs_only_the_id`; журнал backend | Выполнено |
| REQ-006 | Каскад удаляет оценки; описано в `docs/admin.md` | Выполнено |
| REQ-007 | UI-тест «every saved story has a labelled delete button»; замер `opacity` на 1280 и 390px | Выполнено |
| REQ-008 | UI-тест «cancelled by its button or escape»; ручная проверка фокуса | Выполнено |
| REQ-009 | UI-тесты «deleting another story…», «deleting the open story…»; ручная проверка | Выполнено |
| REQ-010 | UI-тесты «a failed delete…», «already deleted elsewhere…», «a 401 on delete…» | Выполнено |
| REQ-011 | UI-тест «delete buttons are locked while the agent answers» | Выполнено |

## Документация

По ревью обновлены:

- `docs/dialogs.md`;
- `docs/admin.md`;
- `docs/README.md`;
- `frontend/README.md`;
- `AGENTS.md`.
