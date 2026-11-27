# Наблюдаемость BM25 и `search_lore`

## Цель

По журналу понимать, что именно нашёл BM25 и сколько фрагментов реально ушло в контекст агента, не записывая текст запроса, фрагменты и идентификаторы документов.

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
- REQ-005: текст запроса, фрагменты, заголовки, `document_id` и `chunk_id` в журнал не попадают.
- REQ-006: `search_lore` при `unavailable` пишет событие с нулевыми
  `passage_count` и `context_chars`.

## Границы

- Всегда: только стабильные числовые поля и статусы.
- Сначала спросить: новые категории пользовательских данных в журнале.
- Никогда: не логировать запрос, фрагменты, заголовки и внутренние id.
