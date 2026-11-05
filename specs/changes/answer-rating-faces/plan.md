# План: оценка истории мордашками Смешариков

Спецификация: [spec.md](./spec.md). Реализуется поверх
[answer-feedback](../answer-feedback/spec.md) в ветке
`feat/user-dialog-history`.

## Порядок

Рискованная часть — миграция с переносом данных — идёт первой и
проверяется на временной PostgreSQL. Затем домен, API, статистика, SVG,
frontend чата и админки, документация, ручная проверка.

## Решения

- В домене балл — `int` 1–5: `StoredMessage.feedback: int | None`,
  `set_feedback(owner_id, dialog_id, message_id, score: int)`.
  `FeedbackValue` удаляется. Диапазон проверяют API (Pydantic `StrictInt`,
  `ge=1`, `le=5`, поэтому `true` и `"5"` отклоняются) и `CHECK` в БД.
  Константы `MIN_SCORE`/`MAX_SCORE` объявлены в `dialogs/models.py`.
- `FeedbackStats(answers_total, rated_answers, counts: tuple[int, ...])`:
  `counts` всегда содержит 5 элементов, `NO_FEEDBACK` содержит пять нулей.
  SQL считает `count().filter(score == n)` для n = 1…5.
- Миграция `0004`: добавить `score` (nullable), выполнить `UPDATE … CASE`,
  установить `NOT NULL` и `CHECK`, удалить `CHECK` и столбец `value`.
  Downgrade выполняет обратный перенос (3–5 → `like`, 1–2 → `dislike`).
- Мордашки хранятся в пяти файлах `frontend/src/static/faces/{1-ezhik,2-nyusha,3-losyash,4-kopatych,5-krosh}.svg`,
  перенесённых из согласованного макета. Каждый файл самодостаточен, у
  градиентов собственные id. Обе HTML-страницы содержат
  `<template id="saiFacesTemplate">` с пятью `<img data-score>`; JS клонирует
  нужный `img`. Vite переписывает `src` в хешированные пути.
- Фразы и подписи шкалы хранятся в одной таблице в `script.js`. В админке
  подписи берутся из `alt` в шаблоне.

## Задача 1. Миграция и PostgreSQL-хранилище

**Требования:** REQ-001, REQ-003 (хранение).

**Критерии приёмки:**
- после upgrade с `0003` значения `like`/`dislike` становятся 5/1;
- `CHECK` отклоняет 0 и 6;
- `set_feedback`/`clear_feedback`/`transcript` работают с баллами.

**Файлы:**
- `db/migrations/versions/0004_feedback_score.py`;
- `db/tables.py`, `db/history.py`;
- `dialogs/{models,history,__init__}.py`;
- `tests/integration/db/test_postgres_history.py`.

**Проверка:** на временном `postgres:17-alpine`
`TEST_DATABASE_URL=… uv run --project backend --locked pytest backend/tests/integration/db/test_postgres_history.py`.

## Задача 2. Домен и сервис

**Требования:** REQ-003, REQ-010.

**Критерии приёмки:**
- in-memory хранилище ставит, меняет и снимает балл;
- `AgentService` журналирует `score`;
- поле `score` есть в `_SAFE_FIELDS`, поле `feedback` удалено.

**Файлы:**
- `application/agent_service.py`, `observability.py`;
- `tests/unit/dialogs/test_history.py`,
  `tests/unit/application/test_agent_service.py`.

**Проверка:** `uv run --project backend --locked pytest backend/tests/unit`.

## Задача 3. HTTP API

**Требования:** REQ-002, REQ-003.

**Критерии приёмки:**
- `204` для 1 и 5;
- `422` для 0, 6, `2.5`, `true`, `"5"` и `{"value":"like"}`;
- история отдаёт `feedback` числом;
- `401`, `404` и `503` не меняются.

**Файлы:**
- `api/{app,schemas}.py`;
- `tests/integration/api/test_message_feedback.py`.

**Проверка:** `uv run --project backend --locked pytest backend/tests/integration/api`.

## Задача 4. Статистика администратора

**Требования:** REQ-008.

**Критерии приёмки:**
- `counts` по окну;
- поля `likes` и `dislikes` удалены;
- точный JSON в API-тесте.

**Файлы:**
- `admin/models.py`, `db/admin_stats.py`, `api/admin.py`;
- `tests/unit/admin/test_admin_stats_service.py`,
  `tests/integration/api/test_admin_stats.py`,
  `tests/integration/db/test_postgres_admin_stats.py`.

**Проверка:** `uv run --project backend --locked pytest backend/tests` и
отдельно DB-тесты с `TEST_DATABASE_URL`.

## Задача 5. Мордашки и чат

**Требования:** REQ-004…REQ-007.

**Критерии приёмки:**
- пять кнопок с `aria-label` и `aria-pressed`;
- выбор, смена и снятие оценки;
- фраза Смешарика;
- откат при ошибке;
- восстановление из истории;
- у ошибки кнопок нет;
- подпись при наведении и фокусе (CSS).

**Файлы:**
- `frontend/src/static/faces/*.svg`;
- `frontend/src/index.html`, `script.js`, `styles.css`, `agent-api.js`;
- `frontend/tests/{ui,agent-api}.test.js`.

**Проверка:** `npm --prefix frontend test`, `npm --prefix frontend run build`.

## Задача 6. Админка

**Требования:** REQ-009.

**Критерии приёмки:**
- среднее с запятой и мордашка ближайшего балла;
- «оценено N из M ответов»;
- пять полос от 5 к 1;
- «Оценок пока нет»;
- разбор `counts` с отказом при несогласованной сумме.

**Файлы:**
- `frontend/src/admin/{index.html,admin.js,admin-api.js,admin.css}`;
- `frontend/tests/{admin-ui,admin-api}.test.js`.

**Проверка:** `npm --prefix frontend test`.

## Задача 7. Документация и проверка

**Требования:** все.

**Файлы:** `docs/dialogs.md`, `docs/database.md`, `docs/admin.md`,
`frontend/README.md`, `AGENTS.md`, `verification.md`.

**Проверка:**
- `make test`, `make lint`;
- пересборка Compose и `make migrate` на базе с оценками 👍/👎;
- скриншоты чата (компьютер и 390px) и админки через `cdp.mjs`;
- ревью документации.
