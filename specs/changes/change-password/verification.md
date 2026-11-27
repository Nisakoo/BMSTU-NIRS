# Verification: смена пароля в настройках аккаунта

Исторический оригинал: `git show 5af56b5:specs/changes/change-password/verification.md`.

## Результат

- Команды: `make test` — frontend: 201 passed; backend: 423 passed, 40 skipped (тесты PostgreSQL без `TEST_DATABASE_URL`)
- Команды: `TEST_DATABASE_URL=… pytest backend/tests/integration/db` на временном `postgres:17-alpine` — 37 passed
- Команды: `make lint` — All checks passed, 103 files already formatted
- Команды: `npx vite build` (в `frontend/`) — Сборка успешна
- Полный `make run` с живым backend не запускался; поведение проверено тестами на ASGI-приложении, in-memory и PostgreSQL-адаптерах.
- Headless Chrome не уменьшает окно меньше ~500px, поэтому ширина 390px проверена расчётом CSS, а не скриншотом.
- Ветка не слита с `main`: при слиянии к ручке нужно применить проверки из `auth-hardening` и `auth-rate-limit` (`Sec-Fetch-Site`, `415`, rate limiting).
- Выданные ранее access-токены других устройств действуют до своего истечения (до 15 минут), как и задано REQ-005.
