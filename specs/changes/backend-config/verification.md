# Проверка: единый корневой Config для backend

## Результат

Проверка завершена успешно 19 сентября 2026 года. Реализация соответствует
требованиям REQ-001–REQ-017 и всем критериям приёмки спецификации. Корневой
`Config` является immutable-агрегатом двух component-owned подконфигов,
environment читается только общим loader на внешней границе, а bootstrap
получает готовую конфигурацию без скрытых источников.

## Проверка требований

| Требования | Доказательство | Результат |
| --- | --- | --- |
| REQ-001–REQ-003 | `test_config_has_component_owned_nested_configs`, `test_config_and_nested_configs_are_frozen_and_forbid_extra_fields`; ревью `config.py`, `agent/models.py`, `agent/providers/config.py` и направления импортов | Выполнено: существует только `Config(agent, llm)`, `ApplicationConfig` удалён, модели остаются у компонентов |
| REQ-004–REQ-006 | `test_load_config_uses_agent_and_provider_defaults`, `test_load_config_reads_all_supported_values`, `test_load_config_normalizes_blank_optional_provider_values`, `test_explicit_mapping_does_not_read_process_environment`; поиск environment reads | Выполнено: все прежние `AGENT_*`/`LLM_*` значения и defaults сохранены, явный mapping изолирован от process environment |
| REQ-007–REQ-008 | Параметризованные validation-тесты, frozen/extra-тест, `test_config_representation_does_not_reveal_api_key`, `test_config_validation_error_does_not_reveal_api_key`, `test_repeated_loads_create_independent_configs`; ревью module state | Выполнено: ошибки контролируются Pydantic, секрет скрыт, singleton и import-time config отсутствуют |
| REQ-009–REQ-010 | `test_main_loads_config_once_and_passes_it_to_application`, `test_create_application_requires_config`; ревью `main.py` и `bootstrap.py` | Выполнено: entrypoint вызывает loader один раз, `create_application` требует готовый `Config` |
| REQ-011–REQ-012 | `test_bootstrap_passes_exact_component_configs`, `test_explicit_provider_does_not_construct_litellm_provider`, `test_bootstrap_builds_service_with_explicit_provider` | Выполнено: точные экземпляры подконфигов передаются владельцам, explicit provider seam сохранён без production fallback |
| REQ-013–REQ-015 | `rg` по backend source, полный регрессионный набор, ревью dependency/lock и Docker-файлов | Выполнено: `os.environ` встречается только в `config.py`; внутренние слои не импортируют корневой `Config`; environment/Docker/dependencies в рамках изменения не менялись |
| REQ-016 | Ревью `docs/configuration.md`, `docs/README.md`, `docs/agent.md` и `AGENTS.md` | Выполнено: описаны поток, ownership, lifecycle и запрет передачи корня внутренним компонентам |
| REQ-017 | `make test`, `make lint` | Выполнено: 96 тестов прошли без сети и реального LLM, Ruff не обнаружил нарушений |

## Критерии приёмки

- [x] `Config` и `load_config` образуют единственный публичный корневой
  конфигурационный контракт; `ApplicationConfig` отсутствует.
- [x] `Config` immutable, запрещает extra fields и содержит только `agent` и
  `llm` с component-owned типами.
- [x] Все действующие environment values загружаются с прежней обязательностью,
  defaults и валидацией.
- [x] Только `smeshariki_ai.config` читает `os.environ`; config singleton
  отсутствует.
- [x] `main.py` выполняет одну загрузку, а bootstrap не читает environment.
- [x] `Agent` и `LiteLLMProvider` получают точные соответствующие подконфиги.
- [x] Явная fake-подмена требует валидный `Config` и не является fallback.
- [x] HTTP API, agent loop, provider behavior, environment и Docker contract не
  изменены.
- [x] Новые runtime-зависимости не добавлены; lock-файл не менялся в рамках
  `backend-config`.
- [x] Архитектурный каталог и корневые правила обновлены.
- [x] Полные тесты и линтинг проходят.

## Выполненные команды

```sh
uv run --project backend --locked pytest backend/tests/unit/test_backend_config.py
uv run --project backend --locked pytest backend/tests/unit/test_bootstrap.py backend/tests/integration/api/test_dialogs.py
make test
make lint
uv lock --project backend --check
env LLM_MODEL=test/model uv run --project backend --locked python -c "from smeshariki_ai.main import app; assert app.title == 'smeshariki-ai'; print(app.title)"
git diff --check
rg -n "os\.environ|os\.getenv|getenv\(" backend/src
rg -n "from smeshariki_ai\.config import Config|import smeshariki_ai\.config" backend/src
rg -n "ApplicationConfig" backend docs AGENTS.md
```

Результаты итогового прогона:

- `make test`: `96 passed`;
- `make lint`: Ruff checks passed, 35 файлов уже отформатированы;
- `uv lock --check`: lock разрешён успешно, 67 packages;
- runtime smoke test: импортировано приложение `smeshariki-ai` с валидным
  `LLM_MODEL`, сетевой запрос не выполнялся;
- `git diff --check`: ошибок whitespace нет;
- поиск: единственное чтение `os.environ` находится в `config.py`; корневой
  `Config` импортируется только composition root; `ApplicationConfig` остался
  только как отрицательная проверка его отсутствия в тесте.

## Известные ограничения

- Поддерживается только конфигурация из process environment или явно
  переданного mapping; файловый loader, secrets manager и runtime reload не
  входят в согласованный scope.
- Импорт production ASGI-entrypoint требует валидный `LLM_MODEL` и fail-fast
  завершается Pydantic-ошибкой при невалидной конфигурации.
- Корень пока содержит только `agent` и `llm`; будущие component configs
  добавляются отдельными SDD-изменениями.
