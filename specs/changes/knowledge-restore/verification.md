# Проверка: восстановление знаний из журнала ревизий

Дата: 2026-11-15.

Статус: успешно.

## Что проверено

- `KnowledgeStore.revision_history(ref)` читает историю без advisory lock:
  PostgreSQL — в read-only снимке одним запросом, in-memory — из состояния
  процесса.
- `restore` выбирает последнюю или указанную ревизию, проверяет
  `format_version`, разбирает payload доменной моделью и сверяет `id`.
- Dry-run не пишет; `--apply` выполняет одну транзакцию, проверяет целостность
  полного набора и пишет `create`/`update` плюс операцию `restore` в журнал.
- Снимок, равный текущей сущности, не создаёт новую ревизию, но журналируется
  как `restore` с `unchanged=1`.
- Невалидный payload, неподдерживаемая версия и отсутствующая ревизия
  отвергаются безопасно; payload в отчёт и журнал не попадает.
- Миграция `0011` допускает `restore`; `downgrade` переводит существующие
  `restore` в `load`.

## Требования

| Требования | Проверка | Результат |
| --- | --- | --- |
| REQ-001–REQ-004 | `test_restore.py`, `test_cli.py`: dry-run, `--revision`, `--apply`, коды `0/1/2` | Пройдено |
| REQ-005–REQ-006 | `test_restore.py`: invalid payload, id mismatch, unsupported format | Пройдено |
| REQ-007–REQ-010 | `test_restore.py`: create/update/unchanged, missing references, no writes on rejection; PostgreSQL end-to-end | Пройдено |
| REQ-011–REQ-013 | `test_store_contract.py::test_revision_history_is_available_without_a_transaction`, `test_postgres_store.py::test_revision_history_reads_in_a_read_only_snapshot` | Пройдено |
| REQ-014–REQ-016 | `test_restore.py`, `test_cli.py`; `make knowledge-restore` в Compose: dry-run, `--apply`, `REVISION` | Пройдено |
| REQ-017 | `test_restore.py::test_restore_logs_only_safe_fields` | Пройдено |
| REQ-018 | Ревью `docs/rag.md`, `docs/knowledge.md`, `docs/database.md`, `docs/logging.md`, `docs/README.md`, `AGENTS.md` | Пройдено |
| REQ-019 | `make lint`, `make test`, RAG-интеграционные тесты | Пройдено |

## Команды и результаты

```text
make lint
All checks passed!
143 files already formatted

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

Ручной CLI-сценарий на PostgreSQL:

```text
delete episodes/e1 --apply     → удаление, ревизия delete
restore episodes/e1            → dry-run, ревизия 3, БД не изменена
restore episodes/e1 --apply    → восстановление, операция 7
restore episodes/e1 --apply    → unchanged=1, операция 8, новых ревизий нет
```

Перед первым `--apply` потребовалась миграция `0011`: без неё старый check
`rag_loads.operation` не пропускал `restore`, и команда безопасно завершалась
`database_unavailable`. Это ожидаемое следствие правила «Make не применяет
миграции автоматически»; в документации указано выполнить `make migrate`.

## Ограничения и отклонения

- `make knowledge-restore` проверен в Compose на PostgreSQL 17.
- Восстановление одной сущности за вызов; массовое восстановление не
  вводилось.
- Поддерживается только текущая версия формата снимка.

## Критерии приёмки

- [x] `restore` выбирает последнюю/указанную ревизию и работает в dry-run и
      `--apply`.
- [x] Восстановленная сущность проходит проверку целостности; при нарушении
      БД не меняется.
- [x] Создаётся новая ревизия `create`/`update`, журнал получает
      `operation=restore`.
- [x] Невалидный и неподдерживаемый снимок отвергаются без payload.
- [x] `revision_history` реализован для обоих хранилищ без advisory lock.
- [x] Миграция `0011` допускает `restore`, `downgrade` безопасен.
- [x] Отчёт и журнал не содержат содержимого знаний.
- [x] Документация обновлена, diff общих файлов аддитивный.
- [x] `make lint`, `make test` и `make test-integration` проходят.
- [x] Полный запуск `make knowledge-restore` в Compose проверен.
