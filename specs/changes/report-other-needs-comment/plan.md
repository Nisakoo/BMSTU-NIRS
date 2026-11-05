# План: комментарий обязателен для причины «Другое»

Спецификация: [spec.md](./spec.md).

## Задача 1. Backend

**Требования:** REQ-003. `model_validator(mode="after")` в `ReportRequest`:
`reason is OTHER and comment is None` → ошибка валидации (`422` через
`_read_body`). Тест `test_missing_or_blank_comment_is_stored_as_none`
переходит на причину `wrong`.

**Файлы:** `api/schemas.py`, `tests/integration/api/test_message_report.py`.

**Проверка:** `uv run --project backend --locked pytest backend/tests/integration/api/test_message_report.py`.

## Задача 2. Frontend

**Требования:** REQ-001, REQ-002, REQ-004. В `openReport`: `paint()`
учитывает обязательность комментария и ставит `aria-required` и подсказку;
обработчик `input` у поля вызывает `paint()`.

**Файлы:** `frontend/src/script.js`, `frontend/tests/ui.test.js`.

**Проверка:** `cd frontend && npm test`.

## Задача 3. Документация и ручная проверка

`docs/dialogs.md`, `frontend/README.md`; пересборка backend и frontend, CDP.
