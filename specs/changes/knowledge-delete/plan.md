# План: удаление знаний с проверкой ссылок и архивом ревизий

## Порядок и зависимости

Сначала расширяется контракт изменения и журнала, затем оба хранилища учатся
удалять агрегаты, после этого появляется use case и CLI. Рискованное место —
порядок удаления строк при взаимных ссылках и атомарность ревизий; оно
проверяется интеграционными тестами PostgreSQL.

## Задача 1. Контракт изменения и журнал операций

**Требования:** REQ-010–REQ-013.

**Критерии:** `EntityChange.operation` допускает `delete`; `ChangeCounts`
содержит `deleted`; `LoadRecord.operation` и `start_load(..., operation)`
различают `load` и `delete`; миграция `0010` добавляет
`rag_loads.operation`; старые строки читаются как `load`.

**Файлы:** `rag/ports.py`, `rag/tables.py`,
`db/migrations/versions/0010_rag_load_operation.py`,
`backend/tests/integration/rag/test_schema.py`.

**Зависимости:** нет.

**Проверка:**
`uv run --project backend --locked pytest backend/tests/integration/rag/test_schema.py -q`
(с `TEST_DATABASE_URL`).

## Задача 2. Удаление в хранилищах

**Требования:** REQ-007, REQ-014–REQ-016.

**Критерии:** `save` применяет `delete` для PostgreSQL и in-memory; дочерние
строки удаляются раньше корней, корни — в обратном порядке зависимостей;
ревизия `delete` пишется со снимком; журналы не затрагиваются; число запросов
не зависит от числа сущностей.

**Файлы:** `rag/memory.py`, `rag/postgres.py`,
`backend/tests/integration/rag/test_store_contract.py`,
`backend/tests/integration/rag/test_postgres_store.py`.

**Зависимости:** задача 1.

**Проверка:**
`uv run --project backend --locked pytest backend/tests/integration/rag/test_store_contract.py backend/tests/integration/rag/test_postgres_store.py -q`.

## Задача 3. Use case удаления

**Требования:** REQ-001–REQ-009, REQ-017, REQ-018.

**Критерии:** dry-run и `--apply`; проверка существования и целостности;
отчёт с `applied`, `operation_id`, `counts`, `entity_count`, `duration_ms`,
`issues`; при отказе нет изменений; при успехе одна транзакция и запись
журнала.

**Файлы:** `rag/maintenance.py`, `backend/tests/unit/rag/test_delete.py`.

**Зависимости:** задачи 1–2.

**Проверка:**
`uv run --project backend --locked pytest backend/tests/unit/rag/test_delete.py -q`.

## Задача 4. CLI delete и наблюдаемость

**Требования:** REQ-001, REQ-017–REQ-020.

**Критерии:** ссылки `<type>/<id>`, dry-run по умолчанию, `--apply`, коды
`0/1/2`; событие `rag.delete.completed` без `id` и содержимого; безопасные
числовые поля добавлены аддитивно.

**Файлы:** `rag/cli.py`, `rag/maintenance.py`, `observability.py`,
`backend/tests/unit/rag/test_cli.py`.

**Зависимости:** задача 3.

**Проверка:**
`uv run --project backend --locked pytest backend/tests/unit/rag/test_cli.py backend/tests/unit/rag/test_delete.py -q`.

## Задача 5. Make и документация

**Требования:** REQ-019, REQ-021.

**Критерии:** `make knowledge-delete` без `REFS` даёт код `2`, без `APPLY=1`
делает dry-run, не применяет миграции, печатает только отчёт в stdout;
документация и `AGENTS.md` обновлены аддитивно.

**Файлы:** `Makefile`, `docs/rag.md`, `docs/knowledge.md`,
`docs/database.md`, `docs/README.md`, `AGENTS.md`.

**Зависимости:** задача 4.

**Проверка:** ручная проверка Make и ревью документации.

## Задача 6. Полная проверка изменения

**Требования:** REQ-022.

**Критерии:** unit- и PostgreSQL-тесты, линт и форматирование проходят;
сценарии dry-run, отказа по ссылке и успешного удаления воспроизведены.

**Файлы:** `specs/changes/knowledge-delete/verification.md`.

**Зависимости:** задачи 1–5.

**Проверка:**
`make lint`, `make test`, `make test-integration`; при отсутствии
инфраструктуры PostgreSQL-тесты фиксируются как пропущенные с причиной.
