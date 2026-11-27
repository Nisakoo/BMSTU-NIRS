# Verification: дата регистрации вместо статуса пользователя

Исторический оригинал: `git show 5af56b5:specs/changes/admin-user-registered-column/verification.md`.

## Результат

- Команды: `cd frontend && npm test` до реализации — 1 failed: файл UI-тестов не загружался без `formatDay`
- Команды: `make test` — frontend: 182 passed; backend: 400 passed, 38 skipped
- Команды: `docker compose … up -d --build frontend` — контейнер пересобран
