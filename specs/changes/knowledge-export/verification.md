# Проверка: выгрузка знаний из PostgreSQL в пакет

Исторический оригинал: `git show 5af56b5:specs/changes/knowledge-export/verification.md`.

## Результат

- make test 815 passed, 125 skipped ```
- Полный набор интеграционных тестов в Compose (PostgreSQL 17 и Redis 7):
- RAG-часть отдельно:
- 940 passed
- 114 passed
- `make knowledge-export` проверен в Compose на PostgreSQL 17; файлы создаются с UID/GID пользователя хоста.
- Добавление безопасных полей в `observability._SAFE_FIELDS` — единственное аддитивное изменение общего backend-файла.
