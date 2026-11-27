# Проверка: восстановление знаний из журнала ревизий

Исторический оригинал: `git show 5af56b5:specs/changes/knowledge-restore/verification.md`.

## Результат

- make test 815 passed, 125 skipped ```
- Полный набор интеграционных тестов в Compose (PostgreSQL 17 и Redis 7):
- RAG-часть отдельно:
- 940 passed
- 114 passed
- `make knowledge-restore` проверен в Compose на PostgreSQL 17.
- Восстановление одной сущности за вызов; массовое восстановление не вводилось.
- Поддерживается только текущая версия формата снимка.
