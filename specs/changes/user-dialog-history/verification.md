# Verification: постоянная история диалогов пользователя

Исторический оригинал: `git show 5af56b5:specs/changes/user-dialog-history/verification.md`.

## Результат

- 17 пропусков в `make test` — интеграционные тесты PostgreSQL и Redis без `TEST_DATABASE_URL`/`TEST_REDIS_URL`; тесты PostgreSQL отдельно запущены и прошли на временной базе, контейнер после проверки удалён.
- Итоговые команды: `make lint` — `All checks passed!`, 91 файл отформатирован
- Итоговые команды: `make test` — frontend: 98 passed, 0 failed; backend: 279 passed, 17 skipped
- Итоговые команды: `TEST_DATABASE_URL=… pytest backend/tests/integration/db` на временном `postgres:17-alpine` — 14 passed (6 новых тестов `PostgresHistoryStore` и 8 существующих)
- Итоговые команды: `make run` (пересборка Compose), `make migrate` через сервис `migrate` — миграция `0002` применена, `alembic_version = 0002`, таблицы `dialogs`, `messages` созданы рядом с существующими данными аутентификации
- Очередь фоновых запусков и SSE-события по-прежнему находятся в памяти процесса: ответ, который генерировался в момент рестарта, теряется.
- Удаление, переименование диалогов и пагинация списка не реализованы (по спецификации).
- Во время runtime-проверки в локальной базе Compose созданы тестовые пользователи `sdd_krosh` и `sdd_nyusha` с одним диалогом.
