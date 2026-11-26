# План: реранкинг кандидатов лора через LLM

## Задача 1. Порт и LLM-реранкер

- REQ-001, REQ-002, REQ-003; зависит от ничего.
- Файлы: `backend/src/smeshariki_ai/rag/lore/rerank.py`,
  `backend/tests/unit/rag/lore/test_rerank.py`.
- Шаг: `Ranker`, `NoopRanker`, `LLMReranker`, `parse_ranking`; выбранные
  кандидаты первыми, остальные сохраняются; деградация к исходному порядку.
- Проверка: `uv run --project backend --locked --no-sync pytest backend/tests/unit/rag/lore/test_rerank.py`.

## Задача 2. Инструмент и бенчмарк

- REQ-004, REQ-005; зависит от задачи 1.
- Файлы: `rag/lore/tools.py`, `rag/lore/benchmark.py`, `rag/cli.py`,
  `test_tool.py`, `test_benchmark.py`, `test_lore_cli.py`.
- Шаг: необязательный `ranker` в инструменте и бенчмарке, флаг `--rerank`.
- Проверка: `uv run --project backend --locked --no-sync pytest backend/tests/unit/rag/lore`.

## Задача 3. Конфигурация и bootstrap

- REQ-006; зависит от задачи 2.
- Файлы: `rag/config.py`, `config.py`, `bootstrap.py`,
  `test_backend_config.py`, `docker/.env.example`.
- Шаг: `RAG_LORE_RERANK_ENABLED` (по умолчанию `false`), сборка реранкера в
  bootstrap.
- Проверка: `uv run --project backend --locked --no-sync pytest backend/tests/unit/test_backend_config.py`.

## Задача 4. Замер и verify

- REQ-007, REQ-008; зависит от задач 1–3.
- Файлы: `docs/lore.md`, `docs/rag.md`, `AGENTS.md`,
  `specs/changes/lore-llm-rerank/verification.md`.
- Шаг: прогон golden set с `--rerank`; фиксация чисел, решение по флагу;
  `make test`, `make lint`; статус `done`.
