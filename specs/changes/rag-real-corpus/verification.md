# Проверка: реальный корпус RAG

## Результат

Структурированный канон расширен до 84 эпизодов. Реальный benchmark собран
из 30 настоящих документов и прогнан без БД.

## Требования

| Требование | Проверка | Результат |
| --- | --- | --- |
| REQ-001–REQ-003 | `python -m smeshariki_ai.rag check data/knowledge` | Пакет валиден: 84 эпизода, 9 персонажей, 10 локаций, 15 артефактов |
| REQ-004–REQ-005 | `lore-benchmark data/lore-benchmark/lore --questions ... --answers ...` | Метрики ниже |
| REQ-006 | `git status`: `data/` отсутствует в Git | Пройдено |

## Команды

```text
uv run --project backend --locked --no-sync python -m smeshariki_ai.rag check data/knowledge

uv run --project backend --locked --no-sync python -m smeshariki_ai.rag \
  lore-benchmark data/lore-benchmark/lore \
  --questions data/lore-benchmark/questions.yaml \
  --answers data/lore-benchmark/answers.json
```

## Метрики реального benchmark

```text
Документов: 30; вопросов: 15 (обычных 10, ловушек 5); k=5.
Recall@5: 1.000
MRR@5: 0.950
Accuracy: 1.000
Correct Rejection Rate: 1.000
```

`Accuracy` проверяет подготовленные ответы и `required_facts`, а не генерацию
живой LLM. Для проверки модели запускать без `--answers`.

## Ограничения

- Реальный набор и 52 новых эпизода лежат только в игнорируемом `data/`;
  в Git они попадают только через зашифрованный архив, который обновляет
  владелец данных.
- Персонажи новых эпизодов определены по упоминаниям в тексте; глубокое
  извлечение interactions, artifacts и locations не выполнялось.
