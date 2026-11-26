# План: бенчмарк лора через путь search_lore

Порядок: рискованный рефакторинг `select` первым, затем метрики, CLI, обвязка
Make и документация, финальный verify с контрольными прогонами.

## Задача 1. `select` в `LoreContextBuilder`

- REQ-001, REQ-007; критерий «существующие тесты `test_context.py` проходят
  без правок».
- Файлы: `backend/src/smeshariki_ai/rag/lore/context.py`,
  `backend/tests/unit/rag/lore/test_context.py`.
- Шаг: вынести цикл выборки пассажей из `build` в метод
  `select(result, query_terms=()) -> tuple[tuple[LoreHit, str], ...]`
  (хит + финальный текст с учётом общего бюджета символов); `build` строит
  `LoreContext` из результата `select`. Новые тесты: `select` совпадает с
  `build` по составу и обрезке, один пассаж на документ, отсечение
  `min_score`, пустая выборка для запроса из одних имён и пустого результата.
- Проверка:
  `uv run --project backend --locked --no-sync pytest backend/tests/unit/rag/lore/test_context.py`.

## Задача 2. Контекстные метрики в `BenchmarkRunner`

- REQ-002, REQ-003, REQ-004; зависит от задачи 1.
- Файлы: `backend/src/smeshariki_ai/rag/lore/benchmark.py`,
  `backend/tests/unit/rag/lore/test_benchmark.py`.
- Шаг: именованный аргумент `context: LoreContextBuilder | None = None`; при
  заданном билдере один поиск на вопрос с `top_k = max(k, retrieval_k)`,
  прежние метрики — по первым `k` хитам, `select` — из первых `retrieval_k`
  хитов; поля вопроса `context_status`, `context_documents`,
  `context_relevant`; агрегаты `context_recall`, `context_any_relevant`,
  `context_found_rate`, `trap_passage_rate` (`None` без билдера).
- Тесты: детерминированный мини-корпус во временном каталоге с точными
  значениями метрик; `None` без билдера; случай `k > retrieval_k`;
  согласованность агрегатов с per-question значениями.
- Проверка:
  `uv run --project backend --locked --no-sync pytest backend/tests/unit/rag/lore/test_benchmark.py`.

## Задача 3. Флаг `--context` в CLI

- REQ-005; зависит от задачи 2.
- Файлы: `backend/src/smeshariki_ai/rag/cli.py`,
  `backend/tests/unit/rag/lore/test_lore_cli.py`.
- Шаг: флаг `--context` у `lore-benchmark`, передача `LoreContextBuilder()` в
  раннер; текстовый вывод печатает `Context Recall`, `Context Any-Relevant`,
  `Context Found`, `Trap Passage Rate` только при `--context`.
- Тесты: текстовый и JSON-вывод с `--context`; без флага новых строк нет,
  JSON-поля `None`.
- Проверка:
  `uv run --project backend --locked --no-sync pytest backend/tests/unit/rag/lore/test_lore_cli.py`.

## Задача 4. `CONTEXT=1` в Makefile

- REQ-006; зависит от задачи 3.
- Файлы: `Makefile`.
- Шаг: `lore-benchmark` передаёт `--context` при `CONTEXT=1` в обеих ветках
  (с `docker/.env` и без), строка помощи дополнена `[CONTEXT=1]`.
- Проверка: `make -n lore-benchmark DIR=data/lore-golden/lore
  QUESTIONS=data/lore-golden/questions.yaml CONTEXT=1` печатает команду с
  `--context`; без `CONTEXT=1` — без него (ревью, без искусственных тестов).

## Задача 5. Документация

- REQ-008; параллельна задаче 4.
- Файлы: `docs/lore.md`, `docs/rag.md`, `AGENTS.md`.
- Шаг: в `docs/lore.md` — подраздел о контекстном режиме (метрики, semantics
  `trap_passage_rate`, команды с `--context`); в `docs/rag.md` — строка о
  бенчмарке дополнена контекстным режимом; в `AGENTS.md` — пункт каталога 12.
- Проверка: ревью соответствия реализации.

## Задача 6. Verify и контрольные прогоны

- Критерии приёмки спеки; зависит от всех.
- Файлы: `specs/changes/lore-tool-benchmark/verification.md`,
  реестр через CLI-скрипт.
- Шаг: `make test`, `make lint`; прогон golden set с `--context` и без;
  фиксация метрик и команд в `verification.md`; статус `done` через CLI после
  успешной проверки.
