# План: полное название истории, обрезка только по ширине

Спецификация: [spec.md](./spec.md). План согласован вместе со спецификацией.

## Задача 1. Лимит названия (TDD)

**Требование:** REQ-001.

**Тест:** `tests/unit/dialogs/test_history.py`:
- 200 символов остаются как есть;
- 201 символ превращается в 200 и «…».

**Код:** `TITLE_MAX_LENGTH = 200` в `dialogs/models.py`.

**Проверка:** `uv run --project backend --locked pytest backend/tests/unit`.

## Задача 2. Миграция 0005 (TDD)

**Требование:** REQ-002.

**Тест:** `tests/integration/db/test_postgres_history.py`:
- на `0004` записать диалог с обрезанным названием и диалог без
  сообщений;
- upgrade;
- проверить, что название полное, а у пустого диалога — `NULL`.

**Код:** `0005_full_dialog_titles.py`. SQL повторяет `dialog_title`:
- `regexp_replace(btrim(content), '\s+', ' ', 'g')`;
- обрезка до 200 с «…»;
- источник — первое сообщение пользователя по `position`.

**Проверка:** временная PostgreSQL и `TEST_DATABASE_URL`.

## Задача 3. Заголовок во frontend (TDD)

**Требования:** REQ-003…REQ-005.

**Тест:** `ui.test.js`: атрибут `title` у заголовка у сохранённой и у новой
истории.

**Код:**
- `script.js`: `title.title` вместе с `textContent`;
- `styles.css`: на ≤ 820px заголовок до двух строк (`line-clamp`).

**Проверка:** `npm --prefix frontend test`.

## Задача 4. Документация и ручная проверка

**Файлы:** `docs/dialogs.md`, `docs/database.md`, `AGENTS.md`.

**Проверка:**
- `make test`, `make lint`;
- `make migrate` на локальной базе;
- CDP на семи ширинах экрана с длинным названием;
- скриншоты.
