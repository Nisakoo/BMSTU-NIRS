# План: поиск стиля в лоре

1. Модель и порт: `LoreQuery.tags`, `LoreIndex.search(..., tags)`.
   Проверка: unit-тесты моделей и индекса.
2. In-memory: хранение тегов документов и фильтр до `rank`.
   Проверка: `test_index.py`.
3. PostgreSQL: параметр `tags` и фильтр `d.tags && :tags` в SQL.
   Проверка: интеграционный тест поиска.
4. Инструмент: `mode` и карта тегов, описание, лог.
   Проверка: `test_tool.py`.
5. Данные: теги `plot`, `style`, `dialogue`.
   Проверка: `lore-check`.

Итог: `make test`, `make lint`.
