# Проверка: golden set лора

## Результат

Собран честный held-out набор на полном корпусе: 84 документа, 20 обычных
вопросов и 10 ловушек. Вопросы зафиксированы до прогона и не подгонялись.

## Метрики

```text
Документов: 84; вопросов: 30 (обычных 20, ловушек 10); k=5.
Recall@5: 0.450
MRR@5: 0.637
Accuracy: 1.000
Correct Rejection Rate: 1.000
```

## Требования

| Требование | Проверка | Результат |
| --- | --- | --- |
| REQ-001–REQ-003 | `data/lore-golden/`, один прогон | Пройдено |
| REQ-004 | Метрики выше | Зафиксировано |
| REQ-005 | `answers.json` только для правил | Ревью |
| REQ-006 | `data/` отсутствует в Git | Пройдено |

## Команды

```text
uv run --project backend --locked --no-sync python -m smeshariki_ai.rag \
  lore-benchmark data/lore-golden/lore \
  --questions data/lore-golden/questions.yaml \
  --answers data/lore-golden/answers.json
```

## Ограничения

- `Accuracy=1.000` измеряет подготовленные ответы, а не живую LLM.
- `Recall@5=0.450` — честная картина лексического BM25 на полном корпусе;
  формулировки после прогона не менялись.
- Набор не коммитится.
