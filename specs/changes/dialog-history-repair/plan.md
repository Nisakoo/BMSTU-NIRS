# План: dialog-history-repair

Спецификация: [spec.md](spec.md).

## T1. Frontend-тест админки без Web Locks

- Требования: REQ-003.
- Файлы: `frontend/tests/admin-ui.test.js`.
- Шаги: подключить `./no-web-locks.js`, как в остальных UI-тестах.
- Проверка: `npm --prefix frontend test` на Node 24.

## T2. Ограничение идентификаторов

- Требования: REQ-001, REQ-002.
- Файлы: `backend/src/smeshariki_ai/api/schemas.py`, `api/app.py`,
  `api/admin.py`, тесты `backend/tests/integration/api/test_message_feedback.py`,
  `test_message_report.py`, `test_report_news.py`, `test_admin_reports.py`.
- Шаги (RED → GREEN): тесты `422` для идентификаторов вне диапазона, в том
  числе при хранилище, которое ответило бы `503`; затем `DbIdPath`
  (`Path(ge=1, le=2**63-1)`) и `DbId` (`Field`) в схемах.
- Проверка: `uv run --project backend --locked pytest backend/tests/integration/api -q`.

## T3. Документация и пометка спецификации

- Требования: REQ-004, REQ-005.
- Файлы: `specs/changes/dialog-history/spec.md`, `docs/dialogs.md`,
  `docs/admin.md`.
- Проверка: ревью.

## Итог

`make lint`, `make test`.
