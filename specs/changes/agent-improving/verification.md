# Verification: улучшение агента под DeepSeek Flash 1017

Дата: 2026-11-20. Ветка `agent-improving` от `main`.

## Итог

Все требования и критерии приёмки `spec.md` подтверждены. `make test` и
`make lint` проходят. Реальные запросы к `deepseek/deepseek-flash` на 2 и 10
минут возвращают русский plain-text без Markdown и иероглифов; thinking по
умолчанию выключен, при явном включении reasoning не попадает в ответ.
`get_context` и `AGENT_SYSTEM_PROMPT` отсутствуют в активных исходниках,
тестах и документации.

## Окружение

- macOS, Python 3.12.11, Node.js, зависимости из `backend/uv.lock`.
- Локальный `docker/.env`: `LLM_MODEL=deepseek/deepseek-flash`,
  `LLM_TEMPERATURE=0.8`, `LLM_THINKING=false`.
- Пакет знаний `data/knowledge` из 68 сущностей для smoke-проверки
  `lookup_knowledge`.
- Docker Compose доступен для `config`, но daemon для `make test-integration`
  не использовался.

## Требования

| Требование | Проверка | Результат |
| --- | --- | --- |
| REQ-001 | `test_load_config_ignores_unsupported_environment_values`; ручная загрузка `load_config` с `AGENT_SYSTEM_PROMPT=must be ignored`; `grep` по активным исходникам, тестам, Compose и документации; локальный `docker/.env` | Промпт не изменился, активных упоминаний нет, локальная строка удалена |
| REQ-002 | `test_bootstrap_builds_service_with_explicit_provider` ожидает только `lookup_knowledge`; `grep` по `backend/src` и `backend/tests`; smoke `ToolRegistry` | `get_context` отсутствует, `lookup_knowledge` работает |
| REQ-003 | `test_prompts.py`; ревью `agent/prompts/system.md`; реальные ответы модели 2/5/10 минут с проверкой Markdown, HTML, CJK и эмодзи | Промпт содержит plain-text и языковые правила; ответы без Markdown и CJK |
| REQ-004 | `test_config.py`, `test_backend_config.py`; smoke-загрузка `load_config` | `temperature=0.8` по умолчанию, диапазон `0…2`, значение передаётся в `acompletion` |
| REQ-005 | `test_config.py`, `test_litellm.py`, `test_backend_config.py`; smoke с `thinking=false` и `thinking=true` | По умолчанию `thinking={"type": "disabled"}`; при `true` reasoning есть, не-DeepSeek `true` отклоняется |
| REQ-006 | `test_runtime.py` для `2/5/10/None`; `test_litellm.py` для `max_tokens` | `1200/3000/6000/None`; значение передаётся на каждой итерации |
| REQ-007 | `test_stream_adds_thinking_reserve_to_explicit_max_tokens`, `test_stream_omits_max_tokens_when_not_requested` | Резерв `3000` добавляется только при включённом thinking и заданном лимите |
| REQ-008 | Полный `make test`; `FakeLLMProvider` в тестах | Сигнатура с `max_tokens` совместима, поведение fake не изменилось |
| REQ-009 | Ревью `docker/.env.example`, `docker/compose.yaml`, `docs/configuration.md`, `docker/README.md`; `docker compose config --quiet` | Переменные добавлены, Compose валиден, секретов нет |
| REQ-010 | Ревью `docs/agent.md`, `docs/rag.md`, `docs/README.md`, `docker/README.md`, `AGENTS.md`; поиск устаревших упоминаний | Документация соответствует реализации, `get_context` и `AGENT_SYSTEM_PROMPT` не описаны как активные настройки |
| REQ-011 | `make test`, ревью логирования | Текст промпта, сообщений, рассуждений и ответов в журнал не добавлен |
| REQ-012 | Полный `make test`; smoke `lookup_knowledge` | Frontend, SSE, история, аутентификация и RAG не менялись |

## Команды и результаты

```sh
make lint
```

Результат: `All checks passed!`, `149 files already formatted`.

```sh
make test
```

Результат: frontend `219 passed`; backend `850 passed, 125 skipped`.
Пропуски — интеграционные PostgreSQL/Redis тесты без `TEST_DATABASE_URL` и
`TEST_REDIS_URL`; изменение их не затрагивает.

```sh
docker compose --env-file docker/.env -f docker/compose.yaml config --quiet
```

Результат: успешно, `compose config ok`.

```sh
uv run --project backend --locked pytest \
  backend/tests/unit/agent/providers/test_config.py \
  backend/tests/unit/test_backend_config.py \
  backend/tests/unit/agent/providers/test_litellm.py \
  backend/tests/unit/agent/test_runtime.py \
  backend/tests/unit/agent/test_prompts.py \
  backend/tests/unit/test_bootstrap.py \
  backend/tests/unit/rag/test_lookup_tool.py -q
```

Результат: `153 passed`.

## Проверка на реальной модели

Использован `LiteLLMProvider` с локальной конфигурацией
`deepseek/deepseek-flash`, `temperature=0.8`, пакет знаний из 68 сущностей и
`ToolRegistry` только с `lookup_knowledge`.

| Запрос | Результат |
| --- | --- |
| Сказка на 2 минуты, `thinking=false` | 1714 символов; reasoning 0; Markdown/CJK/HTML/эмодзи — 0 |
| Сказка на 5 минут, `thinking=false` | 4217 символов; reasoning 0; Markdown/CJK/HTML — 0 |
| Сказка на 10 минут, `thinking=false` | 7310 символов; reasoning 0; Markdown/CJK/HTML/эмодзи — 0 |
| Сказка на 2 минуты, `thinking=true` | 1737 символов; reasoning 202 символа; Markdown/CJK — 0; reasoning не попал в ответ |

Во всех прогонах список инструментов был `["lookup_knowledge"]`;
`get_context` не вызывался и отсутствовал в определениях.

## Проверка scope

- Удалён только демонстрационный `get_context`; `lookup_knowledge`, RAG,
  HTTP/SSE, frontend, БД и аутентификация не менялись.
- Исторические SDD-артефакты `get-context-example` и
  `agent-system-prompt-resource` не переписывались.
- Новые зависимости не добавлялись.
- Тесты не отключены; существующие тесты обновлены под изменённый контракт.

## Известные ограничения

- `make test-integration` не запускался: Docker daemon недоступен в окружении
  проверки; обычный `make test` пропускает интеграционные PostgreSQL/Redis
  тесты, как и до изменения.
- Проверка plain-text на реальной модели недетерминирована: промпт задаёт
  правило, но не гарантирует его на 100% для любого запроса. Runtime
  сознательно не удаляет Markdown постобработкой.
- `LLM_THINKING` поддержан только для моделей с префиксом `deepseek/`; для
  остальных моделей `true` отклоняется при загрузке конфигурации.
