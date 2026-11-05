# План: ответ пользователю о разборе жалобы

Спецификация: [spec.md](./spec.md). Реализуется в ветке
`feat/user-dialog-history` поверх [message-report](../message-report/spec.md).

## Порядок

Рискованная часть — миграция и запросы новостей с учётом удалённой истории и
повторного разбора — идёт первой и проверяется на временной PostgreSQL. Затем
домен и API пользователя, frontend, документация, ручная проверка.

## Решения

- Пакет `dialogs`: `ReportState` (`StrEnum`: `sent`, `reviewed`),
  `StoredMessage.report: ReportState | None = None` вместо `reported: bool`
  (API продолжает отдавать `reported` как `report is not None`);
  `ReportNews(report_id, dialog_id | None, dialog_title | None)`,
  `REPORT_NEWS_LIMIT = 20`.
- `HistoryStore` получает `report_news(owner_id, *, limit)` и
  `mark_report_news_seen(owner_id, report_ids) -> int` (число отмеченных).
  Новости — жалобы владельца со статусом `resolved`/`dismissed` и
  `seen_at IS NULL`, по убыванию `resolved_at`, затем `id`. Название и
  `dialog_id` берутся через `messages` → `dialogs`; у удалённой истории
  `message_id IS NULL`, поэтому оба поля `null`.
- `InMemoryHistoryStore` хранит в `StoredReport` статус, `resolved_at` и
  `seen_at`; для тестов и in-memory сценариев появляется
  `set_report_status(report_id, status)` (зеркало админской операции).
  `PostgresReportStore.set_status` при `new` обнуляет и `seen_at`.
- API: новый роутер `/api/v1/reports` в `api/app.py` с `current_user` на
  уровне роутера (как у диалогов), ошибки хранилища — через
  `_dialog_errors()` (`503`). Тело отметки — `ReportNewsSeenRequest` со
  `StrictInt`-списком длиной 1–20.
- Frontend: `<div id="saiNews" hidden>` между шапкой и лентой в
  `index.html`. `script.js` после первого успешного `createDialog` в
  `start()` один раз вызывает `api.getReportNews()`; ошибки молча
  игнорируются. «Хорошо» скрывает плашку и вызывает
  `markReportNewsSeen(ids)` без ожидания результата для UI; «Открыть
  историю» дополнительно вызывает `openDialog(dialogId)`. Подпись флажка
  `reviewed` — в `addReport` через параметр состояния вместо `reported`.

## Задача 1. Миграция и PostgreSQL

**Требования:** REQ-001, REQ-002, REQ-003 (выборка), REQ-004 (отметка),
REQ-006 (состояние в истории).

**Критерии приёмки:** `0007` применяется и откатывается; новости только
разобранные и непросмотренные, свои, с `null` для удалённой истории, лимит и
порядок; отметка пропускает чужие и неподходящие id; возврат в `new`
обнуляет `seen_at`; `transcript` отдаёт `sent`/`reviewed`.

**Файлы:** `db/migrations/versions/0007_report_seen_at.py`, `db/tables.py`,
`db/history.py`, `db/reports.py`, `dialogs/{models,history,__init__}.py`,
`tests/integration/db/test_postgres_history.py`,
`tests/integration/db/test_postgres_admin_stats.py`.

**Проверка:** на временном `postgres:17-alpine`
`TEST_DATABASE_URL=… uv run --project backend --locked pytest backend/tests/integration/db`.

## Задача 2. In-memory, сервис и API

**Требования:** REQ-003–REQ-006, REQ-012.

**Критерии приёмки:** `GET`/`POST` новостей по REQ-003–REQ-005; поле
`report` и `reported` в истории; журнал `dialog.report.news_seen` с числом
без текстов.

**Файлы:** `dialogs/history.py`, `application/agent_service.py`,
`api/app.py`, `api/schemas.py`, `observability.py` (поле `count`, если его
нет); тесты `tests/unit/dialogs/test_history.py`,
`tests/unit/application/test_agent_service.py`,
`tests/integration/api/test_report_news.py`,
`tests/integration/api/test_dialog_history.py`.

**Проверка:** `uv run --project backend --locked pytest backend/tests/unit backend/tests/integration/api`.

## Задача 3. Frontend чата

**Требования:** REQ-007–REQ-011.

**Критерии приёмки:** плашка для одной, нескольких и удалённой истории;
«Хорошо» и «Открыть историю» отмечают новости и скрывают плашку; ошибки
загрузки и отметки без сообщений; плашка не повторяется в сессии; подпись
флажка `reviewed`; текст только через `textContent`.

**Файлы:** `frontend/src/agent-api.js`, `frontend/src/script.js`,
`frontend/src/index.html`, `frontend/src/styles.css`,
`frontend/tests/agent-api.test.js`, `frontend/tests/ui.test.js`.

**Проверка:** `cd frontend && npm test`.

## Задача 4. Документация

**Файлы:** `docs/dialogs.md`, `docs/database.md`, `docs/admin.md`,
`docs/README.md`, `frontend/README.md`, `AGENTS.md`.

**Проверка:** ревью; `make test`, `make lint`.

## Задача 5. Ручная проверка

`make migrate`, `make run`: жалоба → «Рассмотрено» в `/admin/` → плашка при
открытии чата → «Хорошо» → после перезагрузки плашки нет; «Отклонить» и
«Открыть историю»; телефон 390px.
