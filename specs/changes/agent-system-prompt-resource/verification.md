# Проверка: системный промпт агента как версионируемый ресурс

## Результат

Проверка завершена успешно 21 сентября 2026 года. Реализация соответствует
требованиям REQ-001–REQ-007 и всем критериям приёмки спецификации.
Production-системный промпт загружается из Markdown package resource,
передаётся runtime через прежний immutable `AgentConfig` и не может быть
переопределён через environment.

## Проверка требований

| Требования | Доказательство | Результат |
| --- | --- | --- |
| REQ-001 | Сборка wheel и просмотр его состава | Выполнено: wheel содержит `smeshariki_ai/agent/prompts/system.md` и Python API загрузчика |
| REQ-002 | `test_load_system_prompt_reads_trimmed_package_resource`, `test_load_system_prompt_does_not_depend_on_current_directory`, `test_load_config_uses_versioned_system_prompt`; runtime smoke из wheel | Выполнено: resource читается через `importlib.resources`, не зависит от CWD и попадает в `Config.agent.system_prompt` |
| REQ-003 | Ревью `agent/runtime.py`, `agent/models.py`, `config.py`; полный regression suite | Выполнено: `Agent` и `AgentConfig` не получили файловой или environment-логики, прежний constructor injection сохранён |
| REQ-004 | `test_load_config_does_not_override_system_prompt_from_environment`; ревью `docker/compose.yaml` и `docker/.env.example`; поиск по production source и Docker | Выполнено: `AGENT_SYSTEM_PROMPT` не читается, не передаётся Compose и отсутствует в шаблоне `.env` |
| REQ-005 | `test_load_system_prompt_rejects_blank_resource`, `test_load_system_prompt_hides_resource_read_error`, `test_load_config_propagates_system_prompt_resource_error` | Выполнено: пустой и недоступный resource приводят к безопасной `SystemPromptResourceError` до создания приложения |
| REQ-006 | Существующие config-тесты и полный `make test` | Выполнено: `AGENT_MAX_ITERATIONS`, LLM-настройки, валидация и bootstrap сохраняют прежнее поведение |
| REQ-007 | Ревью `docs/configuration.md`, `docs/agent.md` и `AGENTS.md` | Выполнено: источник, поток загрузки и обновлённый environment-контракт документированы |

## Критерии приёмки

- [x] Production-промпт загружается из `agent/prompts/system.md` независимо от
  рабочей директории.
- [x] Собранный Python wheel содержит Markdown-resource системного промпта.
- [x] `AGENT_SYSTEM_PROMPT` отсутствует в поддерживаемом Docker/environment
  контракте и не влияет на `load_config`.
- [x] Пустой resource отклоняется до создания приложения.
- [x] `Agent` по-прежнему получает готовый immutable `AgentConfig` и не читает
  внешние источники.
- [x] Архитектурная документация соответствует реализации.
- [x] `make lint` проходит успешно.
- [x] `make test` проходит успешно.

## Выполненные команды

```sh
uv run --project backend --locked pytest backend/tests/unit/agent/test_prompts.py
uv run --project backend --locked pytest backend/tests/unit/test_backend_config.py backend/tests/unit/test_bootstrap.py
make test
make lint
git diff --check
uv build --project backend --wheel --out-dir /private/tmp/smeshariki-ai-wheel.b9cXKj
python3 -m zipfile -l /private/tmp/smeshariki-ai-wheel.b9cXKj/smeshariki_ai-0.1.0-py3-none-any.whl
/Users/nisakoo/Documents/BMSTU-NIRS/backend/.venv/bin/python -I -c "import sys; sys.path.insert(0, '/private/tmp/smeshariki-ai-wheel.b9cXKj/smeshariki_ai-0.1.0-py3-none-any.whl'); from smeshariki_ai.config import load_config; config = load_config({'LLM_MODEL': 'test/model'}); assert config.agent.system_prompt == 'You are a helpful Smeshariki assistant.'; print(config.agent.system_prompt)"
rg -n "AGENT_SYSTEM_PROMPT" backend/src docker
rg -n "os\.environ|os\.getenv|getenv\(" backend/src
git diff --name-only -- backend/pyproject.toml backend/uv.lock
```

Результаты итогового прогона:

- целевой набор загрузчика: `4 passed`;
- целевой набор config/bootstrap: `23 passed`;
- `make test`: `132 passed`;
- `make lint`: Ruff checks passed, 43 файла уже отформатированы;
- `git diff --check`: ошибок whitespace нет;
- wheel собран успешно, `agent/prompts/system.md` присутствует в архиве;
- isolated smoke из wheel загрузил ожидаемый prompt из произвольной рабочей
  директории;
- production source и Docker не содержат `AGENT_SYSTEM_PROMPT`;
- единственное чтение `os.environ` осталось в `smeshariki_ai.config`;
- `backend/pyproject.toml` и `backend/uv.lock` не изменены.

## Проверка scope

- HTTP API, agent loop, provider-контракт и хранение диалогов не менялись.
- Новые runtime- или dev-зависимости не добавлялись.
- Автоматические тесты проверяют поведение загрузчика и конфигурации; тестов на
  одно лишь наличие файлов или документации нет.
- Тесты не отключены и не помечены skip в рамках изменения.

## Известные ограничения

- Поддерживается один production-профиль промпта без шаблонизации, runtime
  reload и внешнего prompt registry.
- Изменение Markdown-resource применяется после сборки нового дистрибутива и
  рестарта backend.
- Оставшаяся в пользовательском локальном `docker/.env` строка
  `AGENT_SYSTEM_PROMPT` игнорируется, поскольку Compose больше не передаёт её
  контейнеру.
