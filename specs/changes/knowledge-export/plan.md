# План: выгрузка знаний из PostgreSQL в пакет

## Порядок и зависимости

Задачи выполняются по порядку. Сначала появляется read-only снимок хранилища,
затем writer пакета, затем use case и CLI. Make и документация завершают
изменение. Рискованное место — атомарная запись каталога и права файлов в
Compose; оно проверяется отдельной задачей.

## Задача 1. Снимок хранилища и индекс ревизий

**Требования:** REQ-001–REQ-003.

**Критерии:** `KnowledgeSnapshot` содержит `KnowledgeSet` и индекс ревизий;
`PostgresKnowledgeStore.snapshot()` читает в `REPEATABLE READ READ ONLY` без
advisory lock; `InMemoryKnowledgeStore.snapshot()` отдаёт согласованное
состояние; ошибки безопасны.

**Файлы:** `rag/ports.py`, `rag/memory.py`, `rag/postgres.py`,
`backend/tests/integration/rag/test_store_contract.py`,
`backend/tests/integration/rag/test_postgres_store.py`.

**Зависимости:** нет.

**Проверка:**
`uv run --project backend --locked pytest backend/tests/integration/rag/test_store_contract.py backend/tests/integration/rag/test_postgres_store.py -q`
(PostgreSQL-часть требует `TEST_DATABASE_URL`, без неё пропускается).

## Задача 2. Writer пакета

**Требования:** REQ-007–REQ-009.

**Критерии:** `write_package` создаёт `package.yaml` и файлы сущностей с
алиасами, без `null` и значений по умолчанию; `read_package` возвращает равный
`KnowledgeSet`; полный и частичный пакеты проходят `check`.

**Файлы:** `rag/package.py`, `backend/tests/unit/rag/test_package.py`.

**Зависимости:** задача 1 не нужна, но выполняется после неё для общего
контракта.

**Проверка:**
`uv run --project backend --locked pytest backend/tests/unit/rag/test_package.py -q`.

## Задача 3. Use case export

**Требования:** REQ-004–REQ-009, REQ-012.

**Критерии:** `export_package` проверяет каталог до БД, читает снимок один раз,
фильтрует типы, возвращает `ExportReport`, не оставляет частичного каталога,
различает `empty_store`, `empty_selection`, `destination_not_empty`,
`stored_data_invalid`, `database_unavailable`, `schema_not_ready`,
`export_failed`.

**Файлы:** `rag/maintenance.py` (новый), `backend/tests/unit/rag/test_export.py`.

**Зависимости:** задачи 1–2.

**Проверка:**
`uv run --project backend --locked pytest backend/tests/unit/rag/test_export.py -q`.

## Задача 4. CLI export и наблюдаемость

**Требования:** REQ-010–REQ-015.

**Критерии:** подкоманда `export` с `--type` и `--format`; коды `0/1/2`;
`check` и `schema` не читают environment; событие `rag.export.completed` без
пути, `id` и содержимого; безопасные числовые поля добавлены аддитивно.

**Файлы:** `rag/cli.py`, `rag/maintenance.py`, `observability.py`,
`backend/tests/unit/rag/test_cli.py`.

**Зависимости:** задача 3.

**Проверка:**
`uv run --project backend --locked pytest backend/tests/unit/rag/test_cli.py backend/tests/unit/rag/test_export.py -q`.

## Задача 5. Make, документация и права файлов

**Требования:** REQ-013, REQ-014, REQ-016.

**Критерии:** `make knowledge-export` требует существующий пустой `DIR`, не
применяет миграции, печатает только отчёт в stdout, запускает контейнер с
UID/GID хоста; документация и устаревшие README актуализированы; общие файлы
изменены аддитивно.

**Файлы:** `Makefile`, `docs/rag.md`, `docs/knowledge.md`, `docs/README.md`,
`AGENTS.md`, `backend/README.md`, `docker/README.md`.

**Зависимости:** задача 4.

**Проверка:** ручная проверка на Linux/WSL; ревью diff документации; повторный
`make knowledge-export` в непустой каталог даёт код `1`.

## Задача 6. Полная проверка изменения

**Требования:** REQ-017.

**Критерии:** unit- и PostgreSQL-тесты проходят; форматирование и линт
чистые; сценарий export → check → load не меняет сущности.

**Файлы:** `specs/changes/knowledge-export/verification.md`.

**Зависимости:** задачи 1–5.

**Проверка:**
`make lint`, `make test`, `make test-integration`; при отсутствии
инфраструктуры PostgreSQL-тесты фиксируются как пропущенные с причиной.
