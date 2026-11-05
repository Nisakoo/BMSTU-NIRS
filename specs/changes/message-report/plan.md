# План: жалобы на ответы агента

Спецификация: [spec.md](./spec.md). Реализуется в ветке
`feat/user-dialog-history` после [message-copy](../message-copy/spec.md).

## Порядок

Рискованная часть — миграция с `ON DELETE SET NULL` и копиями текстов —
идёт первой и проверяется на временной PostgreSQL. Затем домен диалогов,
пользовательский API, домен и API администратора, frontend чата, frontend
админки, документация, ручная проверка.

## Решения

- Пакет `dialogs`: `ReportReason` (`StrEnum`: `scary`, `rude`, `wrong`,
  `other`), `REPORT_COMMENT_MAX_LENGTH = 500`, `ReportExistsError`.
  `HistoryStore.report(owner_id, dialog_id, message_id, reason, comment) -> int`
  проверяет владельца так же, как `set_feedback`, копирует текст ответа и
  ближайшего предыдущего сообщения пользователя и возвращает `id` жалобы.
  `StoredMessage.reported: bool = False`.
- `InMemoryHistoryStore` хранит жалобы отдельно от диалогов; `delete`
  обнуляет в них `message_id`. Для тестов админки in-memory хранилище жалоб
  не требуется — используются фейки, как `FakeStatsStore`.
- Пакет `admin`: `ReportStatus` (`new`, `resolved`, `dismissed`),
  `MessageReport` (без пользователя), `ReportNotFoundError`, контракт
  `ReportStore` (`list_reports(status | None, limit)`,
  `set_status(report_id, status, admin_id)`) и `AdminReportsService` с
  журналированием. `UserStatsSnapshot`/`UserStats` получают `reports_new: int = 0`.
- PostgreSQL: `db/reports.py` — `PostgresReportStore`; `report` в
  `PostgresHistoryStore` вставляет строку и ловит `IntegrityError` по
  `UNIQUE(message_id)` как `ReportExistsError`; `transcript` добавляет
  `exists`-флаг `reported`; `PostgresAdminStatsStore` считает `status = 'new'`.
- API: `POST …/report` в `api/app.py` (схема `ReportRequest` с
  `StrictStr`, обрезкой и `max_length=500`), `201 {"report_id": n}`,
  `409 {"detail":"Already reported."}`. `api/admin.py`: `GET /reports`
  (`status` — `new|resolved|dismissed|all`, default `new`), `PATCH
  /reports/{report_id}`; `install_admin(app, admin_stats, admin_reports)`;
  `bootstrap.py` создаёт `PostgresReportStore` и сервис.
- Frontend чата: кнопка-флажок `sai-report` в `addFeedback`; окно —
  встроенная под ответом панель `sai-report-panel` (`role="dialog"`) с
  радиокнопками причин, `textarea` (`maxlength=500`) и кнопками. Одновременно
  открыта одна панель; `Escape` закрывает её раньше остальных обработчиков.
- Frontend админки: раздел `#reports` в `admin/index.html`, запросы в
  `admin-api.js` (`listReports`, `setReportStatus`), отрисовка в `admin.js`
  через `textContent`; счётчик берётся из `reports_new` статистики и
  обновляется после смены статуса.

## Задача 1. Миграция и хранение жалоб в PostgreSQL

**Требования:** REQ-001, REQ-002, REQ-004 (уникальность), REQ-006.

**Критерии приёмки:** `0006` применяется и откатывается; повтор жалобы —
`ReportExistsError`; удаление диалога оставляет жалобу с `message_id = NULL`
и текстами; `transcript` отдаёт `reported`.

**Файлы:** `db/migrations/versions/0006_message_reports.py`, `db/tables.py`,
`db/history.py`, `dialogs/{models,errors,history,__init__}.py`,
`tests/integration/db/test_postgres_history.py`.

**Проверка:** на временном `postgres:17-alpine`
`TEST_DATABASE_URL=… uv run --project backend --locked pytest backend/tests/integration/db/test_postgres_history.py`.

## Задача 2. In-memory хранилище, сервис и API пользователя

**Требования:** REQ-003–REQ-006, REQ-016.

**Критерии приёмки:** коды `201/401/404/409/422/503`; комментарий
обрезается, пустой — `null`, 501 символ — `422`; `reported` в истории;
журнал без текстов.

**Файлы:** `dialogs/history.py`, `application/agent_service.py`,
`api/app.py`, `api/schemas.py`, тесты `tests/unit/dialogs/test_history.py`,
`tests/unit/application/test_agent_service.py`,
`tests/integration/api/test_message_report.py`.

**Проверка:** `uv run --project backend --locked pytest backend/tests/unit backend/tests/integration/api/test_message_report.py`.

## Задача 3. Домен и API администратора

**Требования:** REQ-011–REQ-014, REQ-016.

**Критерии приёмки:** список с фильтром и лимитом 50 без данных автора;
`PATCH` меняет статус и `resolved_at`, `new` их обнуляет, неизвестный `id` —
`404`; `401/403/503` до валидации; `reports_new` в статистике.

**Файлы:** `admin/{models,stores,service,__init__}.py`, `db/reports.py`,
`db/admin_stats.py`, `api/admin.py`, `bootstrap.py`; тесты
`tests/unit/admin/`, `tests/integration/api/test_admin_reports.py`,
`tests/integration/db/test_postgres_admin_stats.py`.

**Проверка:** `uv run --project backend --locked pytest backend/tests/unit/admin backend/tests/integration/api/test_admin_reports.py backend/tests/integration/api/test_admin_stats.py`
и PostgreSQL-тест с `TEST_DATABASE_URL`.

## Задача 4. Frontend чата

**Требования:** REQ-007–REQ-010, REQ-016.

**Критерии приёмки:** флажок только под завершёнными ответами; окно с
причинами, недоступная «Отправить» без причины, закрытие по «Отмена» и
`Escape`; состояние после `201`/`409`; ошибка оставляет окно с выбором;
`reported: true` из истории; один `refresh` при `401`.

**Файлы:** `frontend/src/agent-api.js`, `frontend/src/script.js`,
`frontend/src/styles.css`, `frontend/tests/agent-api.test.js`,
`frontend/tests/ui.test.js`.

**Проверка:** `cd frontend && npm test`.

## Задача 5. Frontend админки

**Требования:** REQ-015, REQ-016.

**Критерии приёмки:** раздел «Жалобы» в навигации со счётчиком; список,
фильтр, «Рассмотрено»/«Отклонить»/«Вернуть в новые», пометка «история
удалена», «Жалоб нет»; ошибки показываются в блоке ошибки; текст только через
`textContent`.

**Файлы:** `frontend/src/admin/{index.html,admin.js,admin-api.js,admin.css}`,
`frontend/tests/admin-api.test.js`, `frontend/tests/admin-ui.test.js`.

**Проверка:** `cd frontend && npm test`.

## Задача 6. Документация

**Файлы:** `docs/dialogs.md`, `docs/database.md`, `docs/admin.md` (тексты
ответов показываются только в жалобах), `docs/README.md`,
`frontend/README.md`, `AGENTS.md`.

**Проверка:** ревью; `make test`, `make lint`.

## Задача 7. Ручная проверка

`make migrate`, `make run`: жалоба в чате, повторная жалоба, удаление
истории, разбор и смена статуса в `/admin/`.
