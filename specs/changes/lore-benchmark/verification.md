# Проверка: benchmark BM25-поиска по лору

Дата: 2026-11-23.

Статус: успешно.

## Что проверено

- Синтетический набор: 30 документов, 10 обычных вопросов, 5 ловушек.
- У каждого обычного вопроса не менее трёх релевантных документов; у ловушки
  их нет.
- `BenchmarkRunner` строит in-memory индекс и не требует PostgreSQL.
- `Recall@k`, `MRR`, `Accuracy` и `Correct Rejection Rate` считаются
  раздельно для обычных вопросов и ловушек.
- `StaticAnswerer` работает с JSON `{question_id: answer}`; `LiteLLMAnswerer`
  отправляет вопрос и фрагменты в `LLMProvider` и не используется runtime-
  агентом.
- `lore-benchmark` с `--answers` не читает environment и БД; без `--answers`
  использует конфиг LLM.
- Текст вопросов, ответов и документов не логируется.

## Требования

| Требования | Проверка | Результат |
| --- | --- | --- |
| REQ-001–REQ-003 | `test_benchmark.py`: форма фикстуры, `lore-check`, валидация вопросов, ошибки YAML | Пройдено |
| REQ-004–REQ-006 | `test_benchmark.py`: Recall, MRR, Accuracy, CRR, частичный ответ, пустые наборы | Пройдено |
| REQ-007 | `StaticAnswerer`, `LiteLLMAnswerer` с fake `LLMProvider` | Пройдено |
| REQ-008–REQ-010 | `test_lore_cli.py`: text/JSON, `--answers`, коды возврата; `make -n lore-benchmark` | Пройдено |
| REQ-011 | `test_lore_events_do_not_log_text`; review benchmark-кода | Пройдено |
| REQ-012 | Ревью `docs/lore.md`, `docs/rag.md`, `docs/README.md`, `AGENTS.md` | Пройдено |
| REQ-013 | `make lint`, `make test`, `make test-integration` | Пройдено |

## Команды и результаты

```text
make lint
All checks passed!
179 files already formatted

make test
923 passed, 133 skipped (backend Pytest)
219 passed (frontend Node)

make test-integration
1056 passed
```

Ручной прогон benchmark с готовыми ответами:

```text
python -m smeshariki_ai.rag lore-benchmark \
  backend/tests/fixtures/lore_benchmark/lore \
  --questions backend/tests/fixtures/lore_benchmark/questions.yaml \
  --answers backend/tests/fixtures/lore_benchmark/answers.json --k 5

Документов: 30; вопросов: 15 (обычных 10, ловушек 5); k=5.
Recall@5: 0.833
MRR@5: 1.000
Accuracy: 0.900
Correct Rejection Rate: 1.000
```

`Accuracy` ниже 1.0 из-за вопроса q07: эталонный ответ не содержит все
`required_facts`. Это корректно фиксируется метрикой и оставлено как пример
разбора ошибок.

Make-цель проверена через `make -n`: каталог лора, вопросы и ответы
монтируются только для чтения, команда запускается в Compose-сервисе
`migrate`.

## Ограничения и отклонения

- Оценка ответов эвристическая: `required_facts` и маркеры отказа, а не
  семантический судья. Замена — отдельное изменение.
- Реальный LLM в тестах не вызывается; `LiteLLMAnswerer` проверен с
  детерминированным fake `LLMProvider`.
- Набор синтетический; реальные сценарии в репозиторий не коммитятся.
- `k=5` и порог отказа зафиксированы для benchmark; изменение — отдельное
  решение.

## Критерии приёмки

- [x] Набор содержит 30 документов, 10 обычных вопросов и 5 ловушек.
- [x] Четыре метрики считаются корректно, включая пустые наборы.
- [x] `lore-benchmark` работает с `--answers` без БД и environment.
- [x] LLM-режим использует только фрагменты и не входит в runtime агента.
- [x] CLI и Make-цель дают `0/1/2` и текстовый/JSON-отчёт.
- [x] Логи не содержат текстов вопросов и ответов.
- [x] Документация обновлена.
- [x] `make lint`, `make test` и `make test-integration` проходят.
