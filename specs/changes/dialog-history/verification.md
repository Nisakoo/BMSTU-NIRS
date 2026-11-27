# Проверка: постоянная история диалогов

Исторический оригинал: `git show 5af56b5:specs/changes/dialog-history/verification.md`.

## Результат

- Команды: `TEST_DATABASE_URL=postgresql+asyncpg://…@127.0.0.1:55433/test make test` (одноразовый `postgres:17-alpine`) — frontend Node-тесты прошли; backend: 405 passed, 8 skipped
- Команды: `TEST_DATABASE_URL=… uv run --project backend --locked pytest backend/tests/integration/db` — 18 passed, из них 11 новых в `test_postgres_history.py`
- Команды: `make lint` — `All checks passed!`, 103 files already formatted
- Черновики, очередь запусков и SSE-подписки живут в памяти одного процесса.
- `AGENTS.md` по-прежнему упоминает «пустой `ToolRegistry`», хотя bootstrap регистрирует `GetContextTool`. Расхождение было до этого изменения и в его объём не входит.
- В локальной базе остался тестовый пользователь `verify_*` из runtime-проверки.
