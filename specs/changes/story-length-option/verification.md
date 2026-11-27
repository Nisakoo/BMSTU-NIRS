# Verification: выбор длины истории

Исторический оригинал: `git show 5af56b5:specs/changes/story-length-option/verification.md`.

## Результат

- Порядок TDD соблюдён во всех задачах: тесты runtime, сервиса, API, клиента и UI сначала падали, затем прошли.
- Итоговые команды: `make test` — frontend: 116 passed, 0 failed; backend: 299 passed, 17 skipped (интеграционные тесты PostgreSQL/Redis без `TEST_*_URL`)
- Итоговые команды: `make lint` — `All checks passed!`
- Итоговые команды: Пересборка `frontend` и `backend` в Compose, headless Chrome с cookie пользователя — см. ниже
- Длина — ориентир для модели: фактический объём отличается от целевого примерно на 10–15%.
