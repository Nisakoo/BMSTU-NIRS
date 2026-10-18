# Verification: хранилище структурированных знаний в PostgreSQL

Дата проверки: 19 октября 2026 года.

## Результат

Изменение `knowledge-postgres-store` соответствует согласованной
спецификации. Требования подтверждены тестами поведения на in-memory
хранилище и на временном PostgreSQL 17, ручной загрузкой и ревью. Тесты
других модулей проходят на той же БД вместе с миграцией `0003`.

## Проверка требований

| Требования | Подтверждение | Результат |
| --- | --- | --- |
| REQ-001 | Таблицы `rag_*` в схеме `public`; `test_public_schema_reset_of_other_modules_is_compatible` и прогон PostgreSQL-тестов других модулей на одной БД | Пройдено |
| REQ-002–REQ-008 | `test_schema.py`: схема после `upgrade` совпадает с `rag/tables.py` (`compare_metadata`), 23 таблицы, `downgrade` до `0002` и повторный `upgrade`, ограничения отвергают недопустимые строки, `RESTRICT` между агрегатами, `CASCADE` внутри, БД принимает каждое значение реестров | Пройдено |
| REQ-009–REQ-011 | `test_updated_at_changes_only_for_saved_entities`; контракт: журнал загрузок, нумерация ревизий, снимок проходит проверку моделью, откат не оставляет записей; ручная загрузка: 4 строки `rag_loads`, ревизии `create` | Пройдено |
| REQ-012–REQ-015 | `test_store_contract.py` на in-memory и PostgreSQL: чтение без потерь и с порядком списков, замена агрегата с сохранностью ссылающихся агрегатов, сериализация транзакций; `test_query_count_does_not_grow_with_entities` (2 и 50 сущностей) | Пройдено |
| REQ-016 | `test_unreachable_database_is_unavailable` (текст ошибки без адреса), `test_missing_migration_means_schema_not_ready` | Пройдено |
| REQ-017–REQ-022 | `test_load.py`: невалидный пакет не открывает хранилище, первая загрузка, идемпотентная повторная, обновление, частичный пакет, откат при нарушении по данным БД с адресом `db:episodes/film_main`, ссылка вне БД, ошибки хранилища; `test_load_package_end_to_end` на PostgreSQL | Пройдено |
| REQ-023 | `test_cli.py`: текстовый и JSON-отчёт, отменённая загрузка, ошибка конфигурации, коды возврата; ручной запуск `load` с окружением как в Compose: stdout JSON-вывода — валидный JSON | Пройдено |
| REQ-024 | Подсказки `make knowledge-load` без `DIR` и с несуществующим каталогом; ревью цели (миграции, монтирование только для чтения, `FORMAT`) | Пройдено частично, см. ограничения |
| REQ-025 | `conftest.py` и `knowledge_database.py`: пропуск без `TEST_DATABASE_URL`, сброс схемы `public` как в тестах других модулей | Пройдено |
| REQ-026 | Ревью `docs/knowledge.md`, `docs/rag.md`, `docs/database.md`, `docs/README.md`, `AGENTS.md`: удалены только собственные строки о схеме `rag` | Пройдено |

## Выполненные команды

```text
make lint
All checks passed!; 126 files already formatted

make test
frontend: pass 103, fail 0
backend: 569 passed, 57 skipped (PostgreSQL- и Redis-тесты без переменных)

TEST_DATABASE_URL=… uv run --project backend --locked pytest backend/tests
618 passed, 8 skipped (только Redis без TEST_REDIS_URL), временный postgres:17-alpine

python -m smeshariki_ai.db.migrate; python -m smeshariki_ai.rag load <пакет>
окружение как в Compose; первая загрузка — 8 сущностей добавлено;
повторная — все без изменений; --format json — валидный JSON в stdout;
пакет с пересекающимися версиями — отменён, код 1

git diff --numstat origin/main -- Makefile
23 0 Makefile
```

## Ограничения проверки

- `make knowledge-load` не удалось выполнить полностью в среде проверки:
  сборка Docker-образа не может скачать Python-зависимости через сетевой прокси
  этой среды. Команды, которые цель выполняет в контейнере (`migrate` и
  `load`), проверены отдельно с тем же окружением. Полный запуск цели
  выполняется на машине с доступом к PyPI.
- Загрузка через `load_config` импортирует модуль агента, и LiteLLM при
  импорте запрашивает из сети карту цен моделей. Без интернета это добавляет
  около 15 секунд и предупреждение в stderr; stdout и результат не меняются.
  Это поведение модуля агента, а не RAG.
- PostgreSQL-тесты других модулей с недоступной БД ждут таймаут соединения по
  60 секунд, поэтому полный прогон с `TEST_DATABASE_URL` длится около 5 минут.
  Сброс схемы с миграцией `0003` занимает около 0,4 секунды.

## Отклонения от плана

- Контрактный набор находится в одном файле
  `tests/integration/rag/test_store_contract.py`, параметризованном
  хранилищем: тесты из разных каталогов не могут импортировать общий модуль без
  изменения общего `pyproject.toml`. In-memory вариант выполняется в обычном
  `make test`.
- Код миграции `0003` получен из `rag/tables.py` генерацией операций Alembic и
  сохранён как неизменяемый файл без импорта кода приложения.
