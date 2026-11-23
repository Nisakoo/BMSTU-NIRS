# План: benchmark BM25-поиска по лору

## Порядок и зависимости

Сначала набор и модели вопросов, затем runner и метрики, после этого
адаптеры ответов, CLI и документация. Рискованные места — формулировка
`required_facts`, маркеры отказа и корректность `Recall/MRR` на пустых
наборах; они проверяются unit-тестами до CLI.

## Задача 1. Набор и модели вопросов

**Требования:** REQ-001–REQ-003.

**Критерии:** 30 документов, 10 обычных вопросов, 5 ловушек; нормальный
вопрос требует ≥3 документов и факты; ловушка — без документов и фактов;
дубли id и лишние поля отвергаются; ошибки чтения безопасны.

**Файлы:** `backend/tests/fixtures/lore_benchmark/`,
`rag/lore/benchmark.py`,
`backend/tests/unit/rag/lore/test_benchmark.py`.

**Зависимости:** `lore-bm25-core`.

**Проверка:**
`uv run --project backend --locked pytest backend/tests/unit/rag/lore/test_benchmark.py -q`.

## Задача 2. Runner и метрики

**Требования:** REQ-004–REQ-006.

**Критерии:** in-memory индекс без БД; `Recall@k` по уникальным документам;
`MRR` по первому релевантному; `Accuracy` по всем `required_facts`;
`Correct Rejection Rate` по маркерам отказа; пустые наборы дают `null`.

**Файлы:** `rag/lore/benchmark.py`,
`backend/tests/unit/rag/lore/test_benchmark.py`.

**Зависимости:** задача 1.

**Проверка:**
`uv run --project backend --locked pytest backend/tests/unit/rag/lore/test_benchmark.py -q`.

## Задача 3. Адаптеры ответов

**Требования:** REQ-007, REQ-011.

**Критерии:** `StaticAnswerer` берёт JSON по id; `LiteLLMAnswerer` отправляет
вопрос и фрагменты в `LLMProvider` и возвращает финальный текст; сеть в
тестах не используется; текст вопросов и ответов не логируется.

**Файлы:** `rag/lore/benchmark.py`, `rag/lore/benchmark_llm.py`,
`backend/tests/unit/rag/lore/test_benchmark.py`.

**Зависимости:** задача 2.

**Проверка:**
`uv run --project backend --locked pytest backend/tests/unit/rag/lore/test_benchmark.py -q`.

## Задача 4. CLI и Make-цель

**Требования:** REQ-008–REQ-010.

**Критерии:** `lore-benchmark` с `--answers` работает без БД и environment;
без `--answers` использует LLM-конфиг; коды `0/1/2`; text/json-отчёт;
Make-цель монтирует данные только для чтения.

**Файлы:** `rag/cli.py`, `Makefile`,
`backend/tests/unit/rag/lore/test_lore_cli.py`.

**Зависимости:** задача 3.

**Проверка:**
`uv run --project backend --locked pytest backend/tests/unit/rag/lore/test_lore_cli.py -q`.

## Задача 5. Документация

**Требования:** REQ-012.

**Критерии:** описаны набор, метрики, команды, ограничения эвристической
оценки; `docs/README.md` и `AGENTS.md` обновлены аддитивно.

**Файлы:** `docs/lore.md`, `docs/rag.md`, `docs/README.md`, `AGENTS.md`.

**Зависимости:** задача 4.

**Проверка:** ревью документации и diff общих файлов.

## Задача 6. Полная проверка изменения

**Требования:** REQ-013.

**Критерии:** benchmark на фикстуре воспроизводим; unit-, CLI- и
integration-тесты проходят; `make lint`, `make test`,
`make test-integration` успешны.

**Файлы:** `specs/changes/lore-benchmark/verification.md`.

**Зависимости:** задачи 1–5.

**Проверка:** `make lint`, `make test`, `make test-integration`; ручной
`make lore-benchmark` с `ANSWERS`.
