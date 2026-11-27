# Verification: полное название истории, обрезка только по ширине

Исторический оригинал: `git show 5af56b5:specs/changes/dialog-full-title/verification.md`.

## Результат

- Команды: `make test` — frontend: 133 passed; backend: 331 passed, 26 skipped (тесты PostgreSQL/Redis без `TEST_*_URL`)
- Команды: `TEST_DATABASE_URL=… pytest backend/tests/integration/db` на временном `postgres:17-alpine` — 23 passed
- Команды: `make lint` — проходит после `make format`: Ruff переносил длинную строку в новом тесте
- Команды: `make migrate` на локальной базе — `alembic_version = 0005`
