# Проверка: системный промпт агента как версионируемый ресурс

Исторический оригинал: `git show 5af56b5:specs/changes/agent-system-prompt-resource/verification.md`.

## Результат

- Проверка завершена успешно 21 сентября 2026 года. Реализация соответствует требованиям REQ-001–REQ-007 и всем критериям приёмки спецификации. Production-системный промпт загружается из Markdown package resource, передаётся runtime через прежний immutable `AgentConfig` и не может быть переопределён через environment.
- Поддерживается один production-профиль промпта без шаблонизации, runtime reload и внешнего prompt registry.
- Изменение Markdown-resource применяется после сборки нового дистрибутива и рестарта backend.
- Оставшаяся в пользовательском локальном `docker/.env` строка `AGENT_SYSTEM_PROMPT` игнорируется, поскольку Compose больше не передаёт её контейнеру.
