# Проверка: инструмент `search_lore` с контекстным бюджетом

Исторический оригинал: `git show 5af56b5:specs/changes/lore-search-tool/verification.md`.

## Результат

- make test 923 passed, 133 skipped (backend Pytest) 219 passed (frontend Node)
- make test-integration 1056 passed ```
- Интеграционный тест `search_lore` с PostgreSQL прошёл: `test_search_lore_tool_uses_postgres_and_returns_compact_context`.
- Системный промпт и `Agent` не менялись; правила использования инструмента заданы его описанием. Если модель будет игнорировать инструмент или пересказывать фрагменты, потребуется отдельное изменение промпта и story-quality.
- Контекстный бюджет фиксирован: 3 фрагмента, 1600 символов, порог 0.5.
- Benchmark и `story canon` в это изменение не входят.
