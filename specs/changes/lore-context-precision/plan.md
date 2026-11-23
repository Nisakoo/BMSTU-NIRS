# План: точность контекста RAG для сказки

## Задача 1. Абсолютный порог и содержательные термы

- Требования: REQ-001–REQ-005.
- Файлы: `rag/lore/context.py`, `rag/lore/services.py`,
  `rag/lore/tools.py`, `backend/tests/unit/rag/lore/test_context.py`,
  `backend/tests/unit/rag/lore/test_tool.py`.
- Проверка:
  `uv run --project backend --locked --no-sync pytest -q backend/tests/unit/rag/lore/test_context.py backend/tests/unit/rag/lore/test_tool.py`.

## Задача 2. Отсев предметов в story canon

- Требования: REQ-006–REQ-009.
- Файлы: `rag/story_canon.py`, `rag/ports.py`, `rag/memory.py`,
  `rag/postgres.py`, `rag/tools.py`,
  `backend/tests/unit/rag/test_story_canon.py`.
- Проверка:
  `uv run --project backend --locked --no-sync pytest -q backend/tests/unit/rag/test_story_canon.py backend/tests/unit/rag/test_story_canon_tool.py`.

## Задача 3. Документация

- Требования: REQ-008–REQ-009.
- Файлы: `docs/rag.md`, `docs/lore.md`, `AGENTS.md`, `docs/README.md`.
- Проверка: ревью diff; автоматические тесты структуры не нужны.

## Итоговая проверка

- `make test`
- `make lint`
