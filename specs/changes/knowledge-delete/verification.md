# Проверка: удаление знаний с проверкой ссылок и архивом ревизий

Исторический оригинал: `git show 5af56b5:specs/changes/knowledge-delete/verification.md`.

## Результат

- make test 815 passed, 125 skipped ```
- Полный набор интеграционных тестов в Compose (PostgreSQL 17 и Redis 7):
- RAG-часть отдельно:
- 940 passed
- 114 passed
- `make knowledge-delete` проверен в Compose на PostgreSQL 17; миграции автоматически не применяются, как зафиксировано в спецификации.
- `rag_loads` сохраняет имя, но получает `operation`; переименование в `rag_operations` не выполнялось.
