# Бенчмарк лора через путь search_lore

## Цель

Offline-бенчмарк лора сегодня измеряет сырой BM25: первые `k` чанков без
фильтрации. Агент при этом получает другой результат — контекст после
`LoreContextBuilder` (top-10 хитов, не более 3 пассажей, один на документ,
абсолютный `min_score`, отказ от запросов из одних имён). Добавляем режим
`--context`: те же вопросы прогоняются через точную продакшн-логику выбора
пассажей, и отчёт получает контекстные метрики, включая честное поведение
ловушек. Сейчас `Correct Rejection Rate` в offline-режиме обеспечен
заготовленными ответами, а инструмент в продакшне отдаёт фрагменты всем ловушкам
golden set — это расхождение бенчмарк не показывает.

Пользователь бенчмарка — автор контента и разработчик RAG: по контекстным
метрикам видно, что реально видит агент, а не что находит индекс.

## Требования

- REQ-001: выборка пассажей выделяется из `LoreContextBuilder` в отдельный метод
  `select(result, query_terms)`, возвращающий выбранные хиты (с `document_id`)
  и их финальные тексты; `build` формирует `LoreContext` из результата
  `select`. Состав пассажей и обрезка текстов для агента не меняются:
  существующие тесты `test_context.py` проходят без правок.
- REQ-002: `BenchmarkRunner` принимает необязательный именованный аргумент
  `context: LoreContextBuilder | None = None`; без него поведение и метрики
  прежние. При заданном билдере вопрос ищется один раз с
  `top_k = max(k, retrieval_k)`: `Recall@k` и `MRR@k` считаются по первым `k`
  хитам как раньше, а выборка контекста — из первых `retrieval_k` хитов, как в
  `SearchLoreTool`.
- REQ-003: в `BenchmarkReport` добавляются метрики, равные `None` без
  `--context`: `context_recall` — средняя по обычным вопросам доля релевантных
  документов, дошедших до контекста; `context_any_relevant` — доля обычных
  вопросов хотя бы с одним релевантным пассажем; `context_found_rate` — доля
  обычных вопросов со статусом `found`; `trap_passage_rate` — доля ловушек,
  которым инструмент отдал пассажи.
- REQ-004: результат вопроса дополняется полями `context_status`
  (`found`/`empty`), `context_documents` (id документов выбранных пассажей по
  порядку) и `context_relevant` (число релевантных среди них; для ловушек
  `None`). Без `--context` поля принимают значения по умолчанию.
- REQ-005: CLI `lore-benchmark` получает флаг `--context` (по умолчанию
  выключен). Текстовый вывод печатает новые метрики только при `--context`;
  JSON всегда содержит поля (значения `None` без флага). Контрольные значения
  существующих метрик не меняются: Recall@5 golden set остаётся `0.450`,
  MRR@5 — `0.637`.
- REQ-006: `make lore-benchmark` принимает `CONTEXT=1` и передаёт `--context`.
- REQ-007: правило «имена без содержания» и абсолютный `min_score` применяются к
  бенчмарку той же функцией `select`, что и в продакшне; дублирование логики
  выбора пассажей запрещено.
- REQ-008: документация обновляется в том же изменении: раздел Benchmark в
  `docs/lore.md`, строка о бенчмарке в `docs/rag.md` и пункт каталога в
  `AGENTS.md`; SDD-артефакты — в `specs/changes/lore-tool-benchmark/`.

## Сценарии

### Основной сценарий

- Given golden set (`data/lore-golden/`) и `--context`;
- When выполняется `lore-benchmark`;
- Then отчёт содержит прежние `Recall@5 0.450` и `MRR@5 0.637`, а также
  контекстные метрики по фактическому прогону (`context_recall`,
  `context_any_relevant`, `context_found_rate`, `trap_passage_rate`).

### Ошибка или граничный случай

- Given вопрос-ловушка, When контекст получает статус `found`; Then
  `trap_passage_rate` учитывает её как пассаж, полученный ловушкой: отказ в
  продакшне остаётся ответственностью LLM и бенчмарком не имитируется.
- Given `--k 20` при `retrieval_k=10`; Then `Recall@20` считается по 20 хитам,
  а выборка контекста — только из первых 10, как в продакшне.
- Given `--context` не указан; Then текстовый вывод и значения прежних метрик
  совпадают с текущими, JSON-поля контекста равны `None`.
- Given запрос из одних имён персонажей; Then `select` возвращает пустую
  выборку и вопрос получает `context_status = empty`.

## Технологии и структура

Python-код продукта: `rag/lore/context.py` (метод `select`), `rag/lore/benchmark.py`
(аргумент билдера и метрики), `rag/cli.py` (флаг `--context` и вывод), `Makefile`
(`CONTEXT=1`). Тесты: `backend/tests/unit/rag/lore/test_context.py`,
`test_benchmark.py`, `test_lore_cli.py`. Документация: `docs/lore.md`,
`docs/rag.md`, `AGENTS.md`.

## Команды

- Прогон на golden set:
  `uv run --project backend --locked --no-sync python -m smeshariki_ai.rag lore-benchmark data/lore-golden/lore --questions data/lore-golden/questions.yaml --answers data/lore-golden/answers.json --context`
- Через Make/Docker:
  `make lore-benchmark DIR=data/lore-golden/lore QUESTIONS=data/lore-golden/questions.yaml ANSWERS=data/lore-golden/answers.json CONTEXT=1`
- Тесты: `make test`; линт: `make lint`.

## Тестирование

- `test_context.py`: `select` возвращает те же пассажи, что строит `build`
  (состав и обрезка), не более одного на документ, отсекает `min_score`,
  возвращает пустую выборку для запроса из одних имён и пустого результата.
- `test_benchmark.py`: детерминированный мини-корпус во временном каталоге —
  точные значения `context_recall`, `context_any_relevant`,
  `context_found_rate` и `trap_passage_rate`; без билдера новые метрики равны
  `None`; агрегаты согласованы с per-question значениями; при `k > retrieval_k`
  выборка контекста берётся из первых `retrieval_k` хитов.
- `test_lore_cli.py`: текстовый и JSON-вывод с `--context`; без флага новых
  строк в текстовом выводе нет, JSON-поля равны `None`.

## Границы

- Всегда: один путь выборки пассажей (`select`) для инструмента и бенчмарка;
  прежние метрики и их зафиксированные контрольные значения не меняются.
- Сначала спросить: изменение `LiteLLMAnswerer` (пока он получает сырые хиты,
  как раньше); вынос стоп-слов и подбор `min_score`.
- Никогда: не менять формулировки вопросов golden set, не подгонять их под
  выдачу, не коммитить содержимое `data/`.

## Критерии приёмки

- [ ] `make test` проходит успешно; `make lint` без замечаний.
- [ ] Прогон golden set с `--context` воспроизводит `Recall@5 0.450` /
  `MRR@5 0.637` и фиксирует контекстные метрики в `verification.md`.
- [ ] Прогон без `--context` не меняет прежний вывод и метрики.
- [ ] Существующие тесты `test_context.py` проходят без изменений.
- [ ] Документация (`docs/lore.md`, `docs/rag.md`, `AGENTS.md`) отражает режим
  `--context`.

## Открытые вопросы

- Нет.
