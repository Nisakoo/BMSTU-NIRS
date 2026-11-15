# Проверка: оптимистичная блокировка изменений знаний по ревизиям

Дата: 2026-11-15.

Статус: успешно.

## Что проверено

- `export` пишет `revisions` в `package.yaml` для выгруженных сущностей с
  ревизией больше `0`; пакет без поля остаётся валидным.
- `check` отвергает неизвестный каталог, неверный `id`, неположительную
  ревизию и ревизию для отсутствующей в пакете сущности.
- `load` читает ожидаемые и текущие ревизии в одной транзакции; при конфликте
  отменяет весь пакет и не пишет `rag_loads`/`rag_revisions`.
- Пакеты без `revisions` загружаются по прежним правилам; новые сущности без
  ревизии создаются.
- Событие `rag.load.completed` содержит `conflict_count` и не содержит `id` и
  содержимого знаний.

## Требования

| Требования | Проверка | Результат |
| --- | --- | --- |
| REQ-001–REQ-002 | `test_store_contract.py::test_snapshot_reads_the_current_state`, `test_revision_index_contains_current_revisions`; `test_postgres_store.py` | Пройдено |
| REQ-003–REQ-005 | `test_export.py` (manifest с ревизиями), `test_cli.py` (`schema`) | Пройдено |
| REQ-006–REQ-008 | `test_package.py`: `test_manifest_revisions_are_normalized`, invalid revisions, missing entity, invalid file без каскада | Пройдено |
| REQ-009–REQ-013 | `test_load.py`: matching revision, conflict, missing entity, multiple conflicts, package without revisions; PostgreSQL end-to-end | Пройдено |
| REQ-014 | `test_load.py`, `test_cli.py`; конфликт в CLI даёт код `1` | Пройдено |
| REQ-015 | `test_load.py::test_load_event_has_only_safe_fields`; `conflict_count` в `_SAFE_FIELDS` | Пройдено |
| REQ-016 | Ревью `docs/knowledge.md`, `docs/rag.md`, `docs/README.md`, `AGENTS.md`, README | Пройдено |
| REQ-017 | `make lint`, `make test`, RAG-интеграционные тесты | Пройдено |

## Команды и результаты

```text
make lint
All checks passed!
139 files already formatted

make test
815 passed, 125 skipped
```

Полный набор интеграционных тестов в Compose (PostgreSQL 17 и Redis 7):

```text
make test-integration
940 passed
```

RAG-часть отдельно:

```text
make test-integration PYTEST_ARGS="backend/tests/integration/rag -x"
114 passed
```

Ручной end-to-end сценарий:

```text
load package                 → загрузка 1
export package               → revisions: classic: 1, series: 1, e1: 1, pin: 1
load exported package        → все сущности без изменений
edit e1, load                → обновление, ревизия e1 становится 2
revert e1, load              → revision_mismatch, «ожидалась ревизия 1, в БД 2», код 1
```

## Ограничения и отклонения

- `format_version` остаётся `1`; `revisions` — необязательное поле manifest.
  Пакеты без него полностью совместимы.
- Схема `rag_*` не менялась, новых миграций нет.
- Sidecar и флаги `--no-revisions`/`--no-lock` не вводились.
- Проверка выполнена в Compose на PostgreSQL 17.

## Критерии приёмки

- [x] `export` пишет текущие ревизии выгруженных сущностей.
- [x] `check` принимает пакеты с метаданными и без них, отвергает неверные.
- [x] `load` отменяется при конфликте и не оставляет изменений в БД и журналах.
- [x] Отчёт перечисляет все конфликты с номерами ревизий или отсутствием
      сущности.
- [x] Пакеты без `revisions` загружаются по прежним правилам.
- [x] Событие `rag.load.completed` содержит `conflict_count`.
- [x] Документация обновлена, diff общих файлов аддитивный.
- [x] `make lint` и `make test` проходят; RAG-интеграционные тесты проходят.
