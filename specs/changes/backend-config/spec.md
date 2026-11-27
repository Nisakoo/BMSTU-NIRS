# Единый корневой Config для backend

## Цель

Сделать `smeshariki_ai.config` единственной общей точкой загрузки и сборки конфигурации всего backend. Модуль должен один раз преобразовывать внешнее
environment в неизменяемый корневой объект `Config`, разбитый на типизированные подконфиги компонентов, после чего composition root передаёт каждому компоненту только принадлежащий ему подконфиг.

Текущее смешанное представление — плоские поля агента рядом с вложенным
`llm_provider` в `ApplicationConfig` — заменяется единообразной структурой
`Config(agent=..., llm=...)`. Загрузка environment выносится из
`create_application` в самый внешний entrypoint backend, чтобы bootstrap
получал только готовую конфигурацию и не имел скрытых источников данных.

Изменение зависит от завершённых спецификаций [`agent-runtime`](../agent-runtime/spec.md), [`agent-dialog-api`](../agent-dialog-api/spec.md) и [`litellm-provider`](../litellm-provider/spec.md).

## Допущения

- Корневой класс называется ровно `Config` и импортируется как
  `from smeshariki_ai.config import Config`.
- `Config` является корневым агрегатом backend, но не глобальным singleton. Экземпляр создаётся на внешней границе процесса и явно передаётся дальше.
- В текущей реализации существуют только два настраиваемых компонента: agent runtime и LiteLLM-провайдер. Подконфиги будущих API, RAG, embeddings, Qdrant и других частей не создаются преждевременно.
- `AgentConfig` остаётся в модуле агента, а `LiteLLMProviderConfig` — в подмодуле провайдеров. Общий модуль агрегирует component-owned модели, но не дублирует и не переносит их определения.
- Существующие имена environment variables, обязательность `LLM_MODEL`, defaults и правила валидации сохраняются без изменения внешнего контракта.
- Для текущего объёма общий публичный модуль остаётся файлом
  `smeshariki_ai/config.py`. Разбиение его реализации на package не входит в
  это изменение.
- Загрузка `.env` остаётся ответственностью Docker Compose. Python-модуль читает переданное отображение либо `os.environ` и не добавляет файловый
  `.env` loader.

## Требования

- REQ-001: В `smeshariki_ai.config` должен существовать корневой Pydantic-класс
  `Config`, запрещающий неизвестные поля и изменение значений после создания.
  Класс `ApplicationConfig` должен быть удалён и не поддерживаться как второй тип корневой конфигурации.
- REQ-002: `Config` должен содержать ровно два поля верхнего уровня:
  `agent: AgentConfig` и `llm: LiteLLMProviderConfig`. Плоские поля
  `agent_system_prompt`, `agent_max_iterations` и поле `llm_provider` в корневом
  объекте должны быть удалены.
- REQ-003: `AgentConfig` и `LiteLLMProviderConfig` должны оставаться в модулях компонентов и сохранять действующие правила валидации. `smeshariki_ai.config`
  импортирует и агрегирует их; agent runtime и provider не должны импортировать корневой `Config`.
- REQ-004: `load_config(environ=None) -> Config` должен быть единственной точкой чтения `os.environ` в backend. Для детерминированных тестов функция должна
  принимать любое `Mapping[str, str]` и при его передаче не обращаться к process environment.
- REQ-005: `load_config` должен собирать `Config.agent` из
  `AGENT_SYSTEM_PROMPT` и `AGENT_MAX_ITERATIONS`, сохраняя текущие defaults:
  `"You are a helpful Smeshariki assistant."` и `4`.
- REQ-006: `load_config` должен собирать `Config.llm` из обязательного
  `LLM_MODEL` и необязательных `LLM_API_KEY`, `LLM_BASE_URL`,
  `LLM_TIMEOUT_SECONDS`, `LLM_NUM_RETRIES`, сохраняя текущие defaults и
  blank-to-`None` поведение необязательных значений.
- REQ-007: Отсутствующий `LLM_MODEL`, неизвестные поля при прямом создании
  `Config`, невалидные agent/provider значения и попытка изменить корневой или
  вложенный подконфиг должны завершаться контролируемой Pydantic-ошибкой до создания FastAPI-приложения. API key не должен раскрываться в представлении объекта или сообщении валидации.
- REQ-008: Модуль `smeshariki_ai.config` не должен создавать `Config` при импорте, хранить mutable global state или экспортировать module-level singleton. Повторные явные вызовы `load_config` должны создавать независимые
  immutable-объекты из переданных источников.
- REQ-009: ASGI-entrypoint должен вызвать `load_config()` ровно один раз и передать готовый `Config` в `create_application`. Это является штатной точкой загрузки конфигурации процесса backend.
- REQ-010: `create_application` должен требовать готовый `Config` и не должен иметь ветку, которая сама вызывает `load_config`, читает environment или подменяет отсутствующую конфигурацию defaults.
- REQ-011: Composition root должен передавать `config.agent` непосредственно в
  `Agent`, а `config.llm` — в `LiteLLMProvider`, не копируя поля и не создавая
  повторно эквивалентные подконфиги. Каждый runtime-компонент получает только свой подконфиг, а не весь корневой `Config`.
- REQ-012: Явная подмена `LLMProvider` в `build_agent_service` и
  `create_application` должна сохраниться для тестов. Она не отменяет
  обязательность валидного корневого `Config` и не становится скрытым production fallback.
- REQ-013: Ни agent runtime, ни LiteLLM provider, ни API/application/dialogs слои не должны самостоятельно читать environment. Будущие backend entrypoints
  должны использовать тот же публичный `load_config`, а не вводить собственные loaders.
- REQ-014: Переход на вложенный `Config` не должен менять имена environment variables, Docker Compose contract, `.env.example`, HTTP API, agent loop, provider behavior, логи или пользовательские ответы.
- REQ-015: Реализация не должна добавлять `pydantic-settings`, dotenv-библиотеку или другую runtime-зависимость. Явное преобразование environment остаётся на Pydantic и стандартной библиотеке.
- REQ-016: Архитектурный каталог должен получить тематическое описание общей конфигурации backend и отразить поток
  `environment -> load_config -> Config -> component configs`. Корневой
  `AGENTS.md` должен закрепить единственную точку чтения environment и запрет
  передачи всего `Config` внутренним компонентам.
- REQ-017: `make test` должен проверять поведение загрузчика, nested config, startup и dependency injection без реального LLM и сети; `make lint` должен успешно проверять итоговый Python-код.

## Границы

- Всегда: иметь один публичный `load_config`; возвращать immutable `Config` с component-owned подконфигами; загружать конфигурацию на внешней границе;
  передавать компоненту только его подконфиг; сохранять текущий environment и Docker contract; скрывать секреты.
- Сначала спросить: переименовать environment variables; добавить новый подконфиг или источник конфигурации; подключить `pydantic-settings`, YAML,
  secrets manager или файловый `.env` loader; превратить `smeshariki_ai.config` в package; настроить reload конфигурации во время работы.
- Никогда: создавать module-level `Config` singleton; читать environment внутри agent/provider/API/application/dialogs; передавать весь `Config` в доменный
  компонент; дублировать поля component config в корневой модели; создавать конфиги ещё не реализованных компонентов; логировать secrets; добавлять структурные тесты только ради файлов или документации.
