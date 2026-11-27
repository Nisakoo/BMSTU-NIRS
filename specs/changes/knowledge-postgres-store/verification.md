# Verification: хранилище структурированных знаний в PostgreSQL

Исторический оригинал: `git show 5af56b5:specs/changes/knowledge-postgres-store/verification.md`.

## Результат

- Изменение `knowledge-postgres-store` соответствует согласованной спецификации. Требования подтверждены тестами поведения на in-memory хранилище и на временном PostgreSQL 17, ручной загрузкой и ревью. Тесты других модулей проходят на той же БД вместе с миграцией `0003`.
- backend: 569 passed, 57 skipped (PostgreSQL- и Redis-тесты без переменных)
- 618 passed, 8 skipped (только Redis без TEST_REDIS_URL), временный postgres:17-alpine
- Контрактный набор находится в одном файле `tests/integration/rag/test_store_contract.py`, параметризованном хранилищем: тесты из разных каталогов не могут импортировать общий модуль без изменения общего `pyproject.toml`. In-memory вариант выполняется в обычном `make test`.
- Код миграции `0003` получен из `rag/tables.py` генерацией операций Alembic и сохранён как неизменяемый файл без импорта кода приложения.
