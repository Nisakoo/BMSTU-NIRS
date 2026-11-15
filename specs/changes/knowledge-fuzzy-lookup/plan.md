# План: нечёткий поиск имён и подсказки при `not_found`

## Порядок и зависимости

Сначала появляется контракт подсказок и in-memory реализация, затем индексы и
PostgreSQL-запросы, после этого fallback в use case и инструменте. Рискованные
места — порог сходства, число запросов и совместимость старого ответа без
`suggestions`; они проверяются контрактными и модульными тестами.

## Задача 1. Контракт подсказок и in-memory suggest

**Требования:** REQ-001–REQ-002.

**Критерии:** `LookupSuggestion` и `suggest` в порту; in-memory считает
триграммное сходство, возвращает каноническое имя, лимит и детерминированный
порядок; точный `find` не меняется.

**Файлы:** `rag/ports.py`, `rag/memory.py`,
`backend/tests/integration/rag/test_reader_contract.py`,
`backend/tests/unit/rag/test_lookup.py`.

**Зависимости:** нет.

**Проверка:**
`uv run --project backend --locked pytest backend/tests/integration/rag/test_reader_contract.py backend/tests/unit/rag/test_lookup.py -q`.

## Задача 2. Индексы pg_trgm и миграция

**Требования:** REQ-004.

**Критерии:** расширение `pg_trgm`; четыре GIN-индекса; `tables.py` совпадает
с миграцией; `downgrade` удаляет только индексы.

**Файлы:** `rag/tables.py`,
`db/migrations/versions/0012_rag_trgm_indexes.py`,
`backend/tests/integration/rag/test_schema.py`.

**Зависимости:** нет.

**Проверка:**
`uv run --project backend --locked pytest backend/tests/integration/rag/test_schema.py -q`.

## Задача 3. PostgreSQL suggest

**Требования:** REQ-003.

**Критерии:** read-only снимок без advisory lock; четыре запроса; порог `0.3`;
канонические имена; лимит; ошибки безопасны.

**Файлы:** `rag/postgres.py`,
`backend/tests/integration/rag/test_postgres_store.py`,
`backend/tests/integration/rag/test_reader_contract.py`.

**Зависимости:** задачи 1–2.

**Проверка:**
`uv run --project backend --locked pytest backend/tests/integration/rag/test_postgres_store.py backend/tests/integration/rag/test_reader_contract.py -q`.

## Задача 4. Fallback и инструмент

**Требования:** REQ-005–REQ-009.

**Критерии:** точный поиск первым; `not_found` с подсказками; пустые подсказки
дают прежний ответ; `unavailable` не маскируется; JSON инструмента и описание
обновлены; `suggestion_count` в журнале.

**Файлы:** `rag/lookup.py`, `rag/tools.py`, `observability.py`,
`backend/tests/unit/rag/test_lookup.py`,
`backend/tests/unit/rag/test_lookup_tool.py`.

**Зависимости:** задачи 1 и 3.

**Проверка:**
`uv run --project backend --locked pytest backend/tests/unit/rag/test_lookup.py backend/tests/unit/rag/test_lookup_tool.py -q`.

## Задача 5. Документация

**Требования:** REQ-010.

**Критерии:** fallback, порог, лимит, подсказки, индексы и миграция описаны;
общие файлы изменены аддитивно.

**Файлы:** `docs/rag.md`, `docs/knowledge.md`, `docs/database.md`,
`docs/logging.md`, `docs/README.md`, `AGENTS.md`.

**Зависимости:** задача 4.

**Проверка:** ревью документации и diff общих файлов.

## Задача 6. Полная проверка изменения

**Требования:** REQ-011.

**Критерии:** unit-, PostgreSQL- и Compose-тесты проходят; точный поиск не
регрессировал; fallback воспроизведён на синтетическом пакете.

**Файлы:** `specs/changes/knowledge-fuzzy-lookup/verification.md`.

**Зависимости:** задачи 1–5.

**Проверка:** `make lint`, `make test`, `make test-integration`; ручной вызов
инструмента с опечаткой.
