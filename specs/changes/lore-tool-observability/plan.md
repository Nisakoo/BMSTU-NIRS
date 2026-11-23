# План: наблюдаемость BM25 и `search_lore`

## Задача 1. Поля безопасного журнала

- Требования: REQ-001, REQ-004.
- Файлы: `observability.py`.
- Проверка:
  `uv run --project backend --locked --no-sync pytest -q backend/tests/unit/test_observability.py`.

## Задача 2. События сервиса и инструмента

- Требования: REQ-001–REQ-003, REQ-006.
- Файлы: `rag/lore/services.py`, `rag/lore/tools.py`.
- Проверка:
  `uv run --project backend --locked --no-sync pytest -q backend/tests/unit/rag/lore/test_services.py backend/tests/unit/rag/lore/test_tool.py`.

## Задача 3. Документация

- Требования: REQ-005.
- Файлы: `docs/logging.md`, `docs/lore.md`.
- Проверка: ревью diff.

## Итоговая проверка

- `make test`
- `make lint`
