# Проверка: бенчмарк лора через путь search_lore

## Результат

Реализован режим `--context` у `lore-benchmark`: те же вопросы прогоняются
через точную продакшн-логику выбора пассажей `search_lore` — общую с
инструментом функцию `LoreContextBuilder.select`. Прежние метрики и вывод без
флага не изменились.

## Требования

| Требование | Проверка | Результат |
| --- | --- | --- |
| REQ-001 | `test_context.py`: `select` совпадает с `build` по составу и обрезке; существующие тесты не правились | Пройдено (17 passed) |
| REQ-002 | `test_benchmark.py`: мини-корпус, `top_k = max(k, retrieval_k)`, срез `hits[:k]` для прежних метрик и `hits[:retrieval_k]` для контекста | Пройдено |
| REQ-003 | `test_benchmark.py`: точные `context_recall`, `context_any_relevant`, `context_found_rate`, `trap_passage_rate`; `None` без билдера | Пройдено |
| REQ-004 | `test_benchmark.py`: `context_status`, `context_documents`, `context_relevant` (`None` у ловушек) | Пройдено |
| REQ-005 | `test_lore_cli.py`: текст и JSON с `--context`; без флага новых строк нет | Пройдено (11 passed) |
| REQ-006 | `make -n lore-benchmark ... CONTEXT=1` печатает `--context` в обеих ветках, без `CONTEXT=1` — нет | Пройдено |
| REQ-007 | Один путь выборки: `build` вызывает `select`, дублирования нет | Пройдено |
| REQ-008 | `docs/lore.md` (раздел и команды), `docs/rag.md`, `AGENTS.md` (пункт 12) | Ревью |

## Команды

```text
make lint
make test
make -n lore-benchmark DIR=data/lore-golden/lore QUESTIONS=data/lore-golden/questions.yaml CONTEXT=1

uv run --project backend --locked --no-sync python -m smeshariki_ai.rag \
  lore-benchmark data/lore-golden/lore \
  --questions data/lore-golden/questions.yaml \
  --answers data/lore-golden/answers.json --context
```

## Результаты

`make test`: 1045 passed, 140 skipped (интеграционные корректно ждут
`TEST_DATABASE_URL`; их запускает `make test-integration`). `make lint` чист.

Golden set (84 документа, 20 обычных + 10 ловушек), `k=5`, без `--context` —
прежние контрольные значения:

```text
Recall@5: 0.450
MRR@5: 0.637
Accuracy: 1.000
Correct Rejection Rate: 1.000
```

Golden set с `--context`:

```text
Context Recall: 0.300
Context Any-Relevant: 0.750
Context Found: 1.000
Trap Passage Rate: 1.000
```

Реальный подобранный набор (30 документов) с `--context`: `Context Recall
0.567`, `Context Any-Relevant 1.000`, `Trap Passage Rate 1.000`.

## Известные ограничения

- `Trap Passage Rate = 1.000` на обоих наборах: инструмент сам не отказывает
  ловушкам; корректный отказ остаётся ответственностью LLM. Бенчмарк это
  фиксирует, а не имитирует.
- `LiteLLMAnswerer` по-прежнему получает сырые хиты (граница спеки);
  выравнивание его контекста с путём инструмента — отдельное изменение.
- Контекстные метрики измеряют выборку пассажей, а не генерацию живой LLM;
  для оценки модели запускать без `--answers`.
- Прогон без `--context` побайтово совпадает с прежним выводом (проверено на
  golden set).
