# План: восстановление знаний из журнала ревизий

## Порядок и зависимости

Сначала появляется read-only история ревизий в порту, затем операция `restore`
в журнале и миграция, после этого use case и CLI. Рискованные места — разбор
снимка без раскрытия payload и проверка ссылок до записи; они проверяются
отдельными тестами.

## Задача 1. История ревизий без advisory lock

**Требования:** REQ-011–REQ-013.

**Критерии:** `KnowledgeStore.revision_history(ref)` реализован для in-memory и
PostgreSQL; PostgreSQL читает в `REPEATABLE READ READ ONLY` одним запросом;
ошибки безопасны; контрактные тесты совпадают с транзакционным
`read_revisions`.

**Файлы:** `rag/ports.py`, `rag/memory.py`, `rag/postgres.py`,
`backend/tests/integration/rag/test_store_contract.py`,
`backend/tests/integration/rag/test_postgres_store.py`.

**Зависимости:** нет.

**Проверка:**
`uv run --project backend --locked pytest backend/tests/integration/rag/test_store_contract.py backend/tests/integration/rag/test_postgres_store.py -q`.

## Задача 2. Операция restore в журнале

**Требования:** REQ-012.

**Критерии:** `JournalOperation` и `LoadRecord` допускают `restore`;
`tables.py` и миграция `0011` обновляют check; `downgrade` переводит
существующие `restore` в `load`; старые строки читаются.

**Файлы:** `rag/ports.py`, `rag/tables.py`,
`db/migrations/versions/0011_rag_restore_operation.py`,
`backend/tests/integration/rag/test_schema.py`.

**Зависимости:** нет.

**Проверка:**
`uv run --project backend --locked pytest backend/tests/integration/rag/test_schema.py -q`.

## Задача 3. Use case восстановления

**Требования:** REQ-002–REQ-010, REQ-014–REQ-015.

**Критерии:** выбор последней/точного номера ревизии; dry-run без записи;
`--apply` в одной транзакции; разбор снимка и проверка id/version; проверка
целостности; create/update/unchanged; новая ревизия и запись `restore` в
журнале; безопасные коды.

**Файлы:** `rag/restore.py`, `backend/tests/unit/rag/test_restore.py`.

**Зависимости:** задачи 1–2.

**Проверка:**
`uv run --project backend --locked pytest backend/tests/unit/rag/test_restore.py -q`.

## Задача 4. CLI и наблюдаемость

**Требования:** REQ-001, REQ-014–REQ-017.

**Критерии:** подкоманда `restore` с `--revision`, `--apply`, `--format`;
коды `0/1/2`; событие `rag.restore.completed` без id, ревизии и содержимого;
dry-run по умолчанию.

**Файлы:** `rag/cli.py`, `rag/restore.py`, `observability.py`,
`backend/tests/unit/rag/test_cli.py`.

**Зависимости:** задача 3.

**Проверка:**
`uv run --project backend --locked pytest backend/tests/unit/rag/test_cli.py backend/tests/unit/rag/test_restore.py -q`.

## Задача 5. Make и документация

**Требования:** REQ-016, REQ-018.

**Критерии:** `make knowledge-restore REF=...` без `REF` даёт код `2`, без
`APPLY=1` — dry-run, миграции автоматически не применяются, stdout содержит
только отчёт; документация и `AGENTS.md` обновлены аддитивно.

**Файлы:** `Makefile`, `docs/rag.md`, `docs/knowledge.md`,
`docs/database.md`, `docs/logging.md`, `docs/README.md`, `AGENTS.md`.

**Зависимости:** задача 4.

**Проверка:** `make -n knowledge-restore REF=characters/pin`; ревью документации.

## Задача 6. Полная проверка изменения

**Требования:** REQ-019.

**Критерии:** unit- и PostgreSQL-тесты, линт и форматирование проходят;
сценарий delete → restore dry-run → restore apply → export воспроизведён.

**Файлы:** `specs/changes/knowledge-restore/verification.md`.

**Зависимости:** задачи 1–5.

**Проверка:**
`make lint`, `make test`, `make test-integration`; при отсутствии
инфраструктуры PostgreSQL-тесты фиксируются как пропущенные с причиной.
