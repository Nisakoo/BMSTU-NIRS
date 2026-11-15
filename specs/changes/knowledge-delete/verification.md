# Проверка: удаление знаний с проверкой ссылок и архивом ревизий

Дата: 2026-11-15.

Статус: успешно.

## Что проверено

- Dry-run по умолчанию и `--apply`; dry-run не пишет в БД и журналы.
- Проверка ссылок и целостности на оставшемся наборе; отказ с адресами
  `db:<каталог>/<id>`.
- Удаление множества сущностей, включая взаимные отношения персонажей.
- Ревизия `delete` со снимком агрегата; журнал `rag_loads` с операцией
  `delete` и счётчиком `deleted`.
- Миграция `0010`; старые строки журнала читаются как `load`.
- Отчёт и журнал не содержат содержимого знаний.

## Требования

| Требования | Проверка | Результат |
| --- | --- | --- |
| REQ-001–REQ-004 | `test_delete.py`: ссылки, dry-run, отказ по ссылкам, отсутствующая сущность; `test_cli.py` | Пройдено |
| REQ-005–REQ-008 | `test_delete.py`, `test_store_contract.py::test_saving_delete_handles_mutual_relationships`; PostgreSQL end-to-end | Пройдено |
| REQ-009–REQ-013 | `test_store_contract.py`, `test_postgres_store.py::test_delete_cascades_child_rows_and_keeps_the_revision`, `test_schema.py::test_load_operation_migration_fills_existing_rows` | Пройдено |
| REQ-014–REQ-016 | Контрактные тесты `save` для in-memory и PostgreSQL; число запросов снимка/поиска | Пройдено |
| REQ-017–REQ-019 | `test_delete.py`, `test_cli.py`; `make knowledge-delete` в Compose: dry-run, `--apply`, повторное удаление | Пройдено |
| REQ-020 | `test_delete.py::test_delete_logs_only_safe_fields`; `deleted_count` в `_SAFE_FIELDS` | Пройдено |
| REQ-021 | Ревью документации и `AGENTS.md` | Пройдено |
| REQ-022 | `make lint`, `make test`, RAG-интеграционные тесты | Пройдено |

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
delete episodes/e1          → dry-run, код 0, БД не изменена
delete episodes/e1 --apply  → операция 4, episodes: 1, код 0
delete episodes/e1 --apply  → entity_not_found, код 1
```

Миграция и старые строки:

```text
downgrade 0009 → INSERT rag_loads(started_at) → upgrade 0010
SELECT operation FROM rag_loads → 'load'
```

## Ограничения и отклонения

- `make knowledge-delete` проверен в Compose на PostgreSQL 17; миграции
  автоматически не применяются, как зафиксировано в спецификации.
- `rag_loads` сохраняет имя, но получает `operation`; переименование в
  `rag_operations` не выполнялось.

## Критерии приёмки

- [x] Dry-run по умолчанию и `--apply` работают по сценариям, коды стабильны.
- [x] Удаление с ссылками из оставшихся сущностей отменяется с адресами `db:`.
- [x] Удаление множества сущностей с взаимными ссылками проходит одной
      транзакцией.
- [x] Для каждой удалённой сущности есть ревизия `delete` со снимком.
- [x] Миграция `0010` добавляет `rag_loads.operation`, старые строки — `load`.
- [x] Отчёт и журнал не содержат содержимого знаний.
- [x] Документация обновлена, diff общих файлов аддитивный.
- [x] `make lint`, `make test` и `make test-integration` проходят.
- [x] Полный запуск `make knowledge-delete` в Compose проверен.
