# План: оптимистичная блокировка изменений знаний по ревизиям

## Порядок и зависимости

Сначала manifest и `check` учатся принимать метаданные ревизий, затем экспорт
начинает их писать, после этого `load` сравнивает ожидаемые и текущие ревизии.
Рискованное место — совместимость пакетов без метаданных и отсутствие частичной
записи при конфликте; оно проверяется отдельными тестами.

## Задача 1. Manifest и проверка ревизий

**Требования:** REQ-004–REQ-008.

**Критерии:** `PackageManifest` принимает необязательное `revisions`;
неизвестный каталог и отсутствующая в пакете сущность дают
`unknown_revision_entity`, неверный `id` или неположительная ревизия —
`invalid_revision`; `check` принимает пакеты без метаданных; невалидный файл
сущности не порождает каскад ошибок ревизий; `package_schema` отражает поле.

**Файлы:** `rag/package.py`, `rag/services.py`,
`backend/tests/unit/rag/test_package.py`,
`backend/tests/unit/rag/test_cli.py`.

**Зависимости:** `knowledge-export` (структура `KnowledgeSnapshot`).

**Проверка:**
`uv run --project backend --locked pytest backend/tests/unit/rag/test_package.py backend/tests/unit/rag/test_cli.py -q`.

## Задача 2. Индекс ревизий и экспорт метаданных

**Требования:** REQ-001–REQ-003.

**Критерии:** `KnowledgeSnapshot.revisions` заполняется обоими хранилищами;
`export` пишет `revisions` в `package.yaml` только для выгруженных сущностей с
ревизией больше `0`; при отсутствии ревизий поле не появляется; порядок
детерминирован.

**Файлы:** `rag/ports.py`, `rag/memory.py`, `rag/postgres.py`,
`rag/maintenance.py`, `rag/package.py`,
`backend/tests/integration/rag/test_store_contract.py`,
`backend/tests/unit/rag/test_export.py`.

**Зависимости:** задача 1.

**Проверка:**
`uv run --project backend --locked pytest backend/tests/integration/rag/test_store_contract.py backend/tests/unit/rag/test_export.py -q`.

## Задача 3. Проверка конфликтов при загрузке

**Требования:** REQ-009–REQ-013.

**Критерии:** `load` читает ожидаемые ревизии из manifest и текущий индекс в
одной транзакции; при несовпадении, отсутствии сущности или ревизии отчёт
содержит `revision_mismatch` с номерами; БД, `rag_loads` и `rag_revisions` не
меняются; пакет без метаданных загружается по старым правилам; новая сущность
без ревизии создаётся.

**Файлы:** `rag/ports.py`, `rag/memory.py`, `rag/postgres.py`,
`rag/services.py`, `backend/tests/unit/rag/test_load.py`,
`backend/tests/integration/rag/test_postgres_store.py`.

**Зависимости:** задачи 1–2.

**Проверка:**
`uv run --project backend --locked pytest backend/tests/unit/rag/test_load.py backend/tests/integration/rag/test_postgres_store.py -q`.

## Задача 4. Отчёт, CLI и наблюдаемость

**Требования:** REQ-014–REQ-015.

**Критерии:** конфликты попадают в `LoadReport.issues`; JSON и текст
сохраняют прежние поля; код `1`; событие `rag.load.completed` содержит
`conflict_count` и не содержит `id` и содержимого.

**Файлы:** `rag/services.py`, `rag/cli.py`, `observability.py`,
`backend/tests/unit/rag/test_load.py`, `backend/tests/unit/rag/test_cli.py`.

**Зависимости:** задача 3.

**Проверка:**
`uv run --project backend --locked pytest backend/tests/unit/rag/test_load.py backend/tests/unit/rag/test_cli.py -q`.

## Задача 5. Документация и устаревшие README

**Требования:** REQ-016.

**Критерии:** `docs/knowledge.md` описывает `revisions`, `docs/rag.md` —
экспорт и конфликт `load`, `AGENTS.md`, `docs/README.md`,
`backend/README.md`, `docker/README.md` актуализированы аддитивно.

**Файлы:** `docs/knowledge.md`, `docs/rag.md`, `docs/README.md`,
`AGENTS.md`, `backend/README.md`, `docker/README.md`.

**Зависимости:** задачи 1–4.

**Проверка:** ревью документации и diff общих файлов.

## Задача 6. Полная проверка изменения

**Требования:** REQ-017.

**Критерии:** unit- и PostgreSQL-тесты, линт и форматирование проходят;
сценарий export → edit → load с конфликтом и без него воспроизведён.

**Файлы:** `specs/changes/knowledge-optimistic-lock/verification.md`.

**Зависимости:** задачи 1–5.

**Проверка:**
`make lint`, `make test`, `make test-integration`; при отсутствии
инфраструктуры PostgreSQL-тесты фиксируются как пропущенные с причиной.
