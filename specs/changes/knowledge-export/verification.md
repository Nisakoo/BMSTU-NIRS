# Проверка: выгрузка знаний из PostgreSQL в пакет

Дата: 2026-11-15.

Статус: успешно.

## Что проверено

- `KnowledgeStore.snapshot()` реализован для PostgreSQL и in-memory.
- PostgreSQL читает снимок в `REPEATABLE READ READ ONLY` без advisory lock
  загрузки; число запросов не зависит от числа сущностей.
- `export` пишет `package.yaml` и файлы сущностей, проходит `check` и
  round-trip `export → load` без изменения сущностей.
- Фильтр `--type`, пустая БД, пустая выборка, непустой каталог и ошибки записи
  дают безопасные коды и не оставляют частичного пакета.
- Отчёт и журнал не содержат пути, `id` и содержимого знаний.

## Требования

| Требования | Проверка | Результат |
| --- | --- | --- |
| REQ-001–REQ-003 | `test_store_contract.py::test_snapshot_reads_the_current_state`, `test_postgres_store.py::test_snapshot_query_count_does_not_grow_with_entities`, `test_snapshot_reads_in_a_read_only_snapshot` | Пройдено |
| REQ-004–REQ-009 | `test_export.py`: полная выгрузка, фильтр, пустая БД/выборка, непустой каталог, ошибка записи, round-trip; `test_package.py` | Пройдено |
| REQ-010–REQ-012 | `test_cli.py`: текст, JSON, коды возврата, ошибки аргументов; `test_export.py` | Пройдено |
| REQ-013–REQ-014 | CLI end-to-end; `make knowledge-export DIR=...` в Compose создал пакет, файлы принадлежат `juve:juve`; повторный запуск в непустой каталог отвергнут | Пройдено |
| REQ-015 | `test_export.py::test_export_logs_only_safe_fields`; поля `entity_count` добавлены в `_SAFE_FIELDS` | Пройдено |
| REQ-016 | Ревью `docs/rag.md`, `docs/knowledge.md`, `docs/README.md`, `AGENTS.md`, `backend/README.md`, `docker/README.md`, `README.md` | Пройдено |
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

Ручной сценарий CLI:

```text
load <package>        → загрузка 1 выполнена
export <empty dir>    → exported=true, entity_count=4, revisions в package.yaml
check <export>        → пакет валиден
load <export>         → все сущности без изменений
```

## Ограничения и отклонения

- `make knowledge-export` проверен в Compose на PostgreSQL 17; файлы создаются
  с UID/GID пользователя хоста.
- Добавление безопасных полей в `observability._SAFE_FIELDS` — единственное
  аддитивное изменение общего backend-файла.

## Критерии приёмки

- [x] `snapshot()` реализован для in-memory и PostgreSQL и проходит контракт;
      PostgreSQL читает без advisory lock.
- [x] `export` создаёт валидный пакет, проходит round-trip и не меняет БД.
- [x] Фильтр, пустая БД/выборка и непустой каталог дают предсказуемые коды.
- [x] CLI и Make-цель описаны и проверены; stdout содержит только отчёт.
- [x] Событие `rag.export.completed` не содержит пути, `id` и знаний.
- [x] Документация обновлена, diff общих файлов аддитивный.
- [x] `make lint`, `make test` и `make test-integration` проходят.
- [x] Полный запуск `make knowledge-export` в Compose проверен.
