# Проверка: оптимистичная блокировка изменений знаний по ревизиям

Исторический оригинал: `git show 5af56b5:specs/changes/knowledge-optimistic-lock/verification.md`.

## Результат

- make test 815 passed, 125 skipped ```
- Полный набор интеграционных тестов в Compose (PostgreSQL 17 и Redis 7):
- RAG-часть отдельно:
- 940 passed
- 114 passed
- `format_version` остаётся `1`; `revisions` — необязательное поле manifest. Пакеты без него полностью совместимы.
- Схема `rag_*` не менялась, новых миграций нет.
- Sidecar и флаги `--no-revisions`/`--no-lock` не вводились.
- Проверка выполнена в Compose на PostgreSQL 17.
