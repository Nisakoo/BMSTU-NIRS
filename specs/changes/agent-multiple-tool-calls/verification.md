# Verification: несколько вызовов инструментов в одном ответе LLM

Исторический оригинал: `git show 5af56b5:specs/changes/agent-multiple-tool-calls/verification.md`.

## Результат

- Все требования и критерии приёмки `spec.md` подтверждены. `make lint` и `make test` проходят. Запрос из раздела «Цель» на настоящих DeepSeek и PostgreSQL получает ответ. Известное ограничение — в конце документа.
- Пропуски backend — интеграционные тесты без `TEST_DATABASE_URL`; изменение их не затрагивает.
- Изредка (2 из 38 запусков) модель пишет текст перед вызовами в одном ответе. Такой ответ по-прежнему считается некорректным (`A response cannot mix text and tool calls`): спецификация сознательно сохранила это правило, а текст к этому моменту уже передан пользователю потоком. Поддержка такого ответа — отдельное изменение.
- uv run --project backend --locked pytest backend/tests/unit/agent   # 94 passed
- make test   # frontend 219/219; backend 833 passed, 125 skipped
