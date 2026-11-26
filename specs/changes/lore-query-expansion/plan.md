# План: расширение запроса через LLM перед BM25

## Задача 1. Порт и реализация расширителя

- REQ-001, REQ-002, REQ-003; зависит от ничего.
- Файлы: `backend/src/smeshariki_ai/rag/lore/expansion.py`,
  `backend/tests/unit/rag/lore/test_expansion.py`.
- Шаг: `QueryExpander`, `LiteLLMQueryExpander`, `parse_expansion`; защитный
  разбор, тихая деградация, событие `lore.query_expansion.completed`.
- Проверка: `uv run --project backend --locked --no-sync pytest backend/tests/unit/rag/lore/test_expansion.py`.

## Задача 2. Инструмент поиска

- REQ-004, REQ-005; зависит от задачи 1.
- Файлы: `backend/src/smeshariki_ai/rag/lore/tools.py`,
  `backend/tests/unit/rag/lore/test_tool.py`.
- Шаг: необязательный `expander`; поиск по «запрос + термины»; правило имён —
  только по исходному запросу.
- Проверка: `uv run --project backend --locked --no-sync pytest backend/tests/unit/rag/lore/test_tool.py`.

## Задача 3. Бенчмарк и CLI

- REQ-006; зависит от задачи 1.
- Файлы: `backend/src/smeshariki_ai/rag/lore/benchmark.py`,
  `backend/src/smeshariki_ai/rag/cli.py`,
  `backend/tests/unit/rag/lore/test_benchmark.py`,
  `backend/tests/unit/rag/lore/test_lore_cli.py`.
- Шаг: `BenchmarkRunner(expander=...)`, флаг `lore-benchmark --expand`.
- Проверка: `uv run --project backend --locked --no-sync pytest backend/tests/unit/rag/lore/test_benchmark.py backend/tests/unit/rag/lore/test_lore_cli.py`.

## Задача 4. Конфигурация и bootstrap

- REQ-007; зависит от задачи 1.
- Файлы: `backend/src/smeshariki_ai/rag/config.py` (новый `RagConfig`),
  `backend/src/smeshariki_ai/config.py`, `backend/src/smeshariki_ai/bootstrap.py`,
  `docker/.env.example`, `backend/tests/unit/test_config.py`,
  `backend/tests/unit/test_bootstrap.py`.
- Шаг: флаг `RAG_QUERY_EXPANSION_ENABLED` (по умолчанию `false`), сборка
  расширителя в bootstrap только при включённом флаге.
- Проверка: `uv run --project backend --locked --no-sync pytest backend/tests/unit/test_config.py backend/tests/unit/test_bootstrap.py`.

## Задача 5. Замер, документация и verify

- REQ-008; зависит от задач 1–4.
- Файлы: `docs/lore.md`, `docs/rag.md`, `AGENTS.md`,
  `specs/changes/lore-query-expansion/verification.md`.
- Шаг: прогон golden set с `--expand`, фиксация чисел; описание флага и
  поведения при сбое; `make test`, `make lint`; статус `done`.
