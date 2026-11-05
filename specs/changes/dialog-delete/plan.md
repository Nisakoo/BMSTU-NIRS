# План: удаление истории из «Мои истории»

Спецификация: [spec.md](./spec.md). План согласован вместе со спецификацией.

## Решения

- **Хранилище.** `HistoryStore.delete(owner_id, dialog_id)` ничего не
  возвращает и бросает `DialogNotFoundError`, если диалог чужой или его
  нет. PostgreSQL выполняет
  `DELETE FROM dialogs WHERE id=:id AND user_id=:owner`; при `rowcount=0`
  — `DialogNotFoundError`. Сообщения и оценки удаляет каскад внешних
  ключей.
- **Сервис.** `AgentService.delete_dialog` удаляет диалог и журналирует
  `dialog.deleted`.
- **Генерация по удалённому диалогу.** Если ответ ещё генерируется, при
  сохранении `append` бросит `DialogNotFoundError`, и уже существующая
  обработка ошибок опубликует `message_error`.
- **Frontend: строка списка.** Строка `li` содержит кнопку истории и
  кнопку-корзину. В режиме подтверждения содержимое `li` заменяется текстом
  и двумя кнопками. Состояние держит переменная `confirmingId`.
- **Frontend: `Escape`.** Обработчик `keydown` на `document` закрывает
  подтверждение, если оно открыто. Уже существующий обработчик панели
  длины остаётся без изменений.
- **Frontend: удаление открытой истории.** Вызывается тот же
  `createDialog()`, что у «+ Новая история».

## Задача 1. Хранилище и сервис

**Требования:** REQ-001, REQ-004, REQ-005.

**Тесты:**
- `tests/unit/dialogs/test_history.py`;
- `tests/unit/application/test_agent_service.py`.

**Проверка:** `uv run --project backend --locked pytest backend/tests/unit`.

## Задача 2. API

**Требования:** REQ-002, REQ-003.

**Тесты:** новый файл `tests/integration/api/test_dialog_delete.py`.

**Проверка:**
`uv run --project backend --locked pytest backend/tests/integration/api`.

## Задача 3. PostgreSQL

**Требование:** REQ-001.

**Тест:** `tests/integration/db/test_postgres_history.py` — каскад и чужой
диалог.

**Проверка:** временная PostgreSQL и `TEST_DATABASE_URL`.

## Задача 4. Клиент API

**Тест:** `frontend/tests/agent-api.test.js` — `deleteDialog`.

## Задача 5. Список с корзиной и подтверждением

**Требования:** REQ-007…REQ-011.

**Тесты:** `frontend/tests/ui.test.js`.

**Код:** `script.js`, `styles.css`.

## Задача 6. Документация и ручная проверка

**Файлы:** `docs/dialogs.md`, `docs/admin.md`, `docs/README.md`,
`frontend/README.md`, `AGENTS.md`.

**Проверка:**
- `make test`, `make lint`;
- пересборка стека;
- CDP на 1280 и 390px;
- скриншоты.
