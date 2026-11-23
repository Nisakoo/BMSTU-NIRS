# Наблюдаемость BM25 и `search_lore`

## Цель

По журналу понимать, что именно нашёл BM25 и сколько фрагментов реально ушло
в контекст агента, не записывая текст запроса, фрагменты и идентификаторы
документов.

## Требования

- REQ-001: `lore.search.completed` содержит `outcome`, `match_count`,
  `hit_count`, `query_term_count`, `top_score`, `index_version`,
  `started_at` и `duration_ms`.
- REQ-002: при ошибке хранилища событие имеет `outcome=failed`,
  `error_type`, `query_term_count` и не содержит текста.
- REQ-003: `SearchLoreTool` пишет `lore.tool.completed` с `outcome`,
  `match_count`, `hit_count`, `passage_count`, `context_chars`,
  `query_term_count`, `started_at` и `duration_ms`.
- REQ-004: новые поля входят в `observability._SAFE_FIELDS`.
- REQ-005: текст запроса, фрагменты, заголовки, `document_id` и `chunk_id` в
  журнал не попадают.
- REQ-006: `search_lore` при `unavailable` пишет событие с нулевыми
  `passage_count` и `context_chars`.

## Сценарии

### Успешный поиск

- Given BM25 нашёл чанки
- When инструмент строит контекст
- Then в журнале есть `top_score`, `hit_count`, `passage_count` и
  `context_chars`.

### Пустой контекст после фильтра

- Given BM25 нашёл чанки, но `min_score` или правило имён их отбросило
- When инструмент завершает работу
- Then `lore.tool.completed` имеет `outcome=empty`, `passage_count=0`.

### Ошибка хранилища

- Given индекс недоступен
- When вызывается инструмент
- Then событие уровня `WARNING` имеет `outcome=unavailable` и не содержит
  текста запроса.

## Технологии и структура

- `rag/lore/services.py` — событие сервиса.
- `rag/lore/tools.py` — событие инструмента.
- `observability.py` — безопасные поля.
- `docs/logging.md`, `docs/lore.md`.

## Команды

- `uv run --project backend --locked --no-sync pytest -q backend/tests/unit/rag/lore/test_tool.py backend/tests/unit/rag/lore/test_services.py backend/tests/unit/test_observability.py`
- `make test`, `make lint`

## Тестирование

| Требования | Проверка |
| --- | --- |
| REQ-001–REQ-003 | `test_services.py`, `test_tool.py`: поля событий и отсутствие текста |
| REQ-004 | `test_observability.py`: безопасные поля принимаются |
| REQ-005–REQ-006 | `caplog`: нет текста, заголовков и id; нулевые счётчики при ошибке |

## Границы

- Всегда: только стабильные числовые поля и статусы.
- Сначала спросить: новые категории пользовательских данных в журнале.
- Никогда: не логировать запрос, фрагменты, заголовки и внутренние id.

## Критерии приёмки

- [x] Оба события содержат нужные счётчики.
- [x] Новые поля разрешены `_SAFE_FIELDS`.
- [x] Тест подтверждает отсутствие текста и id.
- [x] `make test` проходит.

## Открытые вопросы

- Нет.
