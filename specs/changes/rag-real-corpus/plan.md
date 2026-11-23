# План: реальный корпус RAG

## Задача 1. 52 эпизода

- Требования: REQ-001–REQ-003.
- Файлы: `data/knowledge/episodes/*.yaml` (вне Git).
- Проверка: `python -m smeshariki_ai.rag check data/knowledge`.

## Задача 2. Реальный benchmark

- Требования: REQ-004–REQ-005.
- Файлы: `data/lore-benchmark/lore/`, `questions.yaml`, `answers.json`
  (вне Git).
- Проверка:
  `python -m smeshariki_ai.rag lore-benchmark data/lore-benchmark/lore --questions data/lore-benchmark/questions.yaml --answers data/lore-benchmark/answers.json`.

## Задача 3. Документация и метрики

- Требования: REQ-005–REQ-006.
- Файлы: `docs/lore.md`, `AGENTS.md`, `verification.md`.
- Проверка: ревью diff и запись метрик.
