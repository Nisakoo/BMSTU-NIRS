# Verification: улучшение агента под DeepSeek Flash 1017

Исторический оригинал: `git show 5af56b5:specs/changes/agent-improving/verification.md`.

## Результат

- Все требования и критерии приёмки `spec.md` подтверждены. `make test` и `make lint` проходят. Реальные запросы к `deepseek/deepseek-flash` на 2 и 10 минут возвращают русский plain-text без Markdown и иероглифов; thinking по умолчанию выключен, при явном включении reasoning не попадает в ответ. `get_context` и `AGENT_SYSTEM_PROMPT` отсутствуют в активных исходниках, тестах и документации.
- Результат: `All checks passed!`, `149 files already formatted`.
- Результат: frontend `219 passed`; backend `850 passed, 125 skipped`. Пропуски — интеграционные PostgreSQL/Redis тесты без `TEST_DATABASE_URL` и `TEST_REDIS_URL`; изменение их не затрагивает.
- Проверка на реальной модели: Сказка на 2 минуты, `thinking=false` — 1714 символов; reasoning 0; Markdown/CJK/HTML/эмодзи — 0
- Проверка на реальной модели: Сказка на 5 минут, `thinking=false` — 4217 символов; reasoning 0; Markdown/CJK/HTML — 0
- Проверка на реальной модели: Сказка на 10 минут, `thinking=false` — 7310 символов; reasoning 0; Markdown/CJK/HTML/эмодзи — 0
- Проверка на реальной модели: Сказка на 2 минуты, `thinking=true` — 1737 символов; reasoning 202 символа; Markdown/CJK — 0; reasoning не попал в ответ
- Результат: `153 passed`.
- `make test-integration` не запускался: Docker daemon недоступен в окружении проверки; обычный `make test` пропускает интеграционные PostgreSQL/Redis тесты, как и до изменения.
- Проверка plain-text на реальной модели недетерминирована: промпт задаёт правило, но не гарантирует его на 100% для любого запроса. Runtime сознательно не удаляет Markdown постобработкой.
- `LLM_THINKING` поддержан только для моделей с префиксом `deepseek/`; для остальных моделей `true` отклоняется при загрузке конфигурации.
