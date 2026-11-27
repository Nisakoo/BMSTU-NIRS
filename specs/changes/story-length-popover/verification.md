# Verification: выбор длины истории ползунком во всплывающей панели

Исторический оригинал: `git show 5af56b5:specs/changes/story-length-popover/verification.md`.

## Результат

- Команды: `make test` — frontend: 133 passed, 0 failed; backend: 330 passed, 25 skipped (тесты PostgreSQL/Redis без `TEST_*_URL`)
- Команды: `make lint` — 94 файла отформатированы
- Команды: `npm --prefix frontend run build` — успешно
