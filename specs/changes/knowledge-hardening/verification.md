# Verification: надёжность каталога и хранилища знаний

Дата проверки: 19 октября 2026 года.

## Результат

Изменение `knowledge-hardening` соответствует согласованной спецификации.
Исправления подтверждены тестами, которые до исправления падали;
рефакторинг подтверждён прежними тестами поведения, контрактным набором и
подсчётом запросов, прошедшими без изменения проверяемого поведения.

## Проверка требований

| Требования | Подтверждение | Результат |
| --- | --- | --- |
| REQ-001, REQ-002 | `test_load_without_backend_config_is_a_clear_error`, `test_invalid_stored_data_is_not_a_configuration_error`, `test_missing_environment_is_a_configuration_error` (настоящий `load_config`), `test_corrupted_rows_are_reported_as_invalid_data` (строка без имени в PostgreSQL), параметр `stored_data_invalid` в `test_store_failures_are_reported` | Пройдено |
| REQ-003 | Тесты `normalize_name` с «ё» из двух символов и `casefold`; конфликт имён с разложенной «ё» в `test_integrity.py`. До исправления 4 теста падали | Пройдено |
| REQ-004, REQ-006 | `test_missing_manifest`, `test_invalid_manifest` (версия, лишнее поле, нет поля, строка вместо числа), `test_schema_lists_every_entity_type` | Пройдено |
| REQ-005, REQ-007 | Контрактный набор на in-memory и PostgreSQL: ревизии с `format_version`, журнал с типизированными `ChangeCounts`; сравнение схемы после миграции с `rag/tables.py` | Пройдено |
| REQ-008 | `test_check_constraints_allow_exactly_the_registry` для шести словарей | Пройдено |
| REQ-009 | `test_symlinks_are_rejected_and_not_read` (ссылка на файл и на каталог вне пакета) | Пройдено |
| REQ-010, REQ-011 | `Issue` и `unverified` вынесены из домена; импорты `models.py` и `integrity.py` — только стандартная библиотека и Pydantic; прежние тесты проходят | Пройдено |
| REQ-012 | `test_registry.py`: реестр домена, адаптер пакета и преобразователи PostgreSQL покрывают все типы | Пройдено |
| REQ-013 | `rag/postgres_mappers.py`; контрактный набор и `test_query_count_does_not_grow_with_entities` проходят; `postgres.py` сократился с 607 до 246 строк | Пройдено |
| REQ-014 | Ревью `docs/knowledge.md`, `docs/rag.md`, `AGENTS.md`; все YAML-примеры страницы вместе с `package.yaml` проходят `check` | Пройдено |

## Выполненные команды

```text
make lint
All checks passed!; 129 files already formatted

uv run --project backend --locked pytest backend
585 passed, 64 skipped (PostgreSQL- и Redis-тесты без переменных)

TEST_DATABASE_URL=… uv run --project backend --locked pytest backend
641 passed, 8 skipped (только Redis без TEST_REDIS_URL), включая
PostgreSQL-тесты других модулей с миграцией 0003

make knowledge-check DIR=<примеры docs/knowledge.md>
Пакет валиден.

git diff --numstat 1c37b4d -- AGENTS.md
7 0 AGENTS.md (собственный раздел RAG)
```

## Ограничения проверки

- Docker-демон в среде проверки перестал создавать контейнеры, а `npm`
  frontend-тестов завис в ожидании ввода-вывода. Поэтому PostgreSQL-тесты
  выполнены на локальном PostgreSQL 16 без Docker (проект использует 17;
  возможности схемы, включая `NULLS NOT DISTINCT`, доступны с версии 15), а
  frontend-тесты не перезапускались: изменение их не затрагивает.
- Миграция `0003` изменена до первого влития в `main`: добавлена колонка
  `rag_revisions.format_version`, а `rag_loads.report` переименована в
  `counts`. Применённых в `main` миграций изменение не касается.
