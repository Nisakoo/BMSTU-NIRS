# Проверка: наблюдаемость BM25 и `search_lore`

## Результат

События сервиса и инструмента содержат безопасные счётчики, по которым видно
результат BM25 и размер контекста. Текст запроса, фрагменты и внутренние id в
журнал не попадают.

## Требования

| Требование | Проверка | Результат |
| --- | --- | --- |
| REQ-001–REQ-003 | `pytest backend/tests/unit/rag/lore/test_services.py backend/tests/unit/rag/lore/test_tool.py` | Пройдено |
| REQ-004 | `pytest backend/tests/unit/test_observability.py` | Пройдено |
| REQ-005–REQ-006 | `caplog`: нет текста, заголовков и id; нулевые счётчики при ошибке | Пройдено |

## Команды

```text
uv run --project backend --locked --no-sync pytest backend -q
1025 passed, 137 skipped
```

## События

- `lore.search.completed`: `outcome`, `match_count`, `hit_count`,
  `query_term_count`, `top_score`, `index_version`, `started_at`,
  `duration_ms`.
- `lore.tool.completed`: `outcome`, `match_count`, `hit_count`,
  `passage_count`, `context_chars`, `query_term_count`, `started_at`,
  `duration_ms`.

## Ограничения

- `top_score` округляется до трёх знаков и служит для диагностики, а не для
  сравнения прогонов.
- При `unavailable` событие инструмента пишется на уровне `WARNING`.
