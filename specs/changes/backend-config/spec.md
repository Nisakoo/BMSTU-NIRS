# Единый корневой Config для backend

## Цель

Сделать `smeshariki_ai.config` единственной общей точкой загрузки и сборки
конфигурации всего backend. Модуль должен один раз преобразовывать внешнее
environment в неизменяемый корневой объект `Config`, разбитый на типизированные
подконфиги компонентов, после чего composition root передаёт каждому компоненту
только принадлежащий ему подконфиг.

Текущее смешанное представление — плоские поля агента рядом с вложенным
`llm_provider` в `ApplicationConfig` — заменяется единообразной структурой
`Config(agent=..., llm=...)`. Загрузка environment выносится из
`create_application` в самый внешний entrypoint backend, чтобы bootstrap
получал только готовую конфигурацию и не имел скрытых источников данных.

Изменение зависит от завершённых спецификаций
[`agent-runtime`](../agent-runtime/spec.md),
[`agent-dialog-api`](../agent-dialog-api/spec.md) и
[`litellm-provider`](../litellm-provider/spec.md).

## Допущения

- Корневой класс называется ровно `Config` и импортируется как
  `from smeshariki_ai.config import Config`.
- `Config` является корневым агрегатом backend, но не глобальным singleton.
  Экземпляр создаётся на внешней границе процесса и явно передаётся дальше.
- В текущей реализации существуют только два настраиваемых компонента:
  agent runtime и LiteLLM-провайдер. Подконфиги будущих API, RAG, embeddings,
  Qdrant и других частей не создаются преждевременно.
- `AgentConfig` остаётся в модуле агента, а `LiteLLMProviderConfig` — в
  подмодуле провайдеров. Общий модуль агрегирует component-owned модели, но не
  дублирует и не переносит их определения.
- Существующие имена environment variables, обязательность `LLM_MODEL`,
  defaults и правила валидации сохраняются без изменения внешнего контракта.
- Для текущего объёма общий публичный модуль остаётся файлом
  `smeshariki_ai/config.py`. Разбиение его реализации на package не входит в
  это изменение.
- Загрузка `.env` остаётся ответственностью Docker Compose. Python-модуль
  читает переданное отображение либо `os.environ` и не добавляет файловый
  `.env` loader.

## Требования

- REQ-001: В `smeshariki_ai.config` должен существовать корневой Pydantic-класс
  `Config`, запрещающий неизвестные поля и изменение значений после создания.
  Класс `ApplicationConfig` должен быть удалён и не поддерживаться как второй
  тип корневой конфигурации.
- REQ-002: `Config` должен содержать ровно два поля верхнего уровня:
  `agent: AgentConfig` и `llm: LiteLLMProviderConfig`. Плоские поля
  `agent_system_prompt`, `agent_max_iterations` и поле `llm_provider` в корневом
  объекте должны быть удалены.
- REQ-003: `AgentConfig` и `LiteLLMProviderConfig` должны оставаться в модулях
  компонентов и сохранять действующие правила валидации. `smeshariki_ai.config`
  импортирует и агрегирует их; agent runtime и provider не должны импортировать
  корневой `Config`.
- REQ-004: `load_config(environ=None) -> Config` должен быть единственной точкой
  чтения `os.environ` в backend. Для детерминированных тестов функция должна
  принимать любое `Mapping[str, str]` и при его передаче не обращаться к
  process environment.
- REQ-005: `load_config` должен собирать `Config.agent` из
  `AGENT_SYSTEM_PROMPT` и `AGENT_MAX_ITERATIONS`, сохраняя текущие defaults:
  `"You are a helpful Smeshariki assistant."` и `4`.
- REQ-006: `load_config` должен собирать `Config.llm` из обязательного
  `LLM_MODEL` и необязательных `LLM_API_KEY`, `LLM_BASE_URL`,
  `LLM_TIMEOUT_SECONDS`, `LLM_NUM_RETRIES`, сохраняя текущие defaults и
  blank-to-`None` поведение необязательных значений.
- REQ-007: Отсутствующий `LLM_MODEL`, неизвестные поля при прямом создании
  `Config`, невалидные agent/provider значения и попытка изменить корневой или
  вложенный подконфиг должны завершаться контролируемой Pydantic-ошибкой до
  создания FastAPI-приложения. API key не должен раскрываться в представлении
  объекта или сообщении валидации.
- REQ-008: Модуль `smeshariki_ai.config` не должен создавать `Config` при
  импорте, хранить mutable global state или экспортировать module-level
  singleton. Повторные явные вызовы `load_config` должны создавать независимые
  immutable-объекты из переданных источников.
- REQ-009: ASGI-entrypoint должен вызвать `load_config()` ровно один раз и
  передать готовый `Config` в `create_application`. Это является штатной
  точкой загрузки конфигурации процесса backend.
- REQ-010: `create_application` должен требовать готовый `Config` и не должен
  иметь ветку, которая сама вызывает `load_config`, читает environment или
  подменяет отсутствующую конфигурацию defaults.
- REQ-011: Composition root должен передавать `config.agent` непосредственно в
  `Agent`, а `config.llm` — в `LiteLLMProvider`, не копируя поля и не создавая
  повторно эквивалентные подконфиги. Каждый runtime-компонент получает только
  свой подконфиг, а не весь корневой `Config`.
- REQ-012: Явная подмена `LLMProvider` в `build_agent_service` и
  `create_application` должна сохраниться для тестов. Она не отменяет
  обязательность валидного корневого `Config` и не становится скрытым
  production fallback.
- REQ-013: Ни agent runtime, ни LiteLLM provider, ни API/application/dialogs
  слои не должны самостоятельно читать environment. Будущие backend entrypoints
  должны использовать тот же публичный `load_config`, а не вводить собственные
  loaders.
- REQ-014: Переход на вложенный `Config` не должен менять имена environment
  variables, Docker Compose contract, `.env.example`, HTTP API, agent loop,
  provider behavior, логи или пользовательские ответы.
- REQ-015: Реализация не должна добавлять `pydantic-settings`, dotenv-библиотеку
  или другую runtime-зависимость. Явное преобразование environment остаётся на
  Pydantic и стандартной библиотеке.
- REQ-016: Архитектурный каталог должен получить тематическое описание общей
  конфигурации backend и отразить поток
  `environment -> load_config -> Config -> component configs`. Корневой
  `AGENTS.md` должен закрепить единственную точку чтения environment и запрет
  передачи всего `Config` внутренним компонентам.
- REQ-017: `make test` должен проверять поведение загрузчика, nested config,
  startup и dependency injection без реального LLM и сети; `make lint` должен
  успешно проверять итоговый Python-код.

## Сценарии

### Штатный запуск с минимальной конфигурацией

- Given process environment содержит только валидный `LLM_MODEL`
- When ASGI-entrypoint запускается
- Then он один раз вызывает `load_config()`
- And получает `Config` с default `AgentConfig` и default-сетевыми настройками
  `LiteLLMProviderConfig`
- And передаёт готовый объект в `create_application`
- And bootstrap создаёт `Agent` с `config.agent` и `LiteLLMProvider` с
  `config.llm`

### Полностью переопределённые подконфиги

- Given переданное отображение содержит все поддерживаемые `AGENT_*` и `LLM_*`
  переменные
- When вызывается `load_config(environ)`
- Then возвращается `Config`, где значения сгруппированы в `agent` и `llm`
- And process environment не читается
- And секрет доступен только через `SecretStr`, не раскрываясь в представлении
  корневого объекта

### Создание приложения с готовым Config

- Given тест создал валидный `Config` и явный `FakeLLMProvider`
- And process environment отсутствует либо содержит конфликтующие значения
- When вызывается `create_application(config, llm_provider=fake)`
- Then приложение использует переданные `config.agent`, `config.llm` и fake
- And не обращается к `load_config` или process environment

### Ошибка конфигурации при старте

- Given `LLM_MODEL` отсутствует либо одно из числовых или URL-значений
  невалидно
- When entrypoint вызывает `load_config()`
- Then Pydantic validation завершается ошибкой до сборки `AgentService` и
  FastAPI-приложения
- And отсутствующий config не заменяется fake-провайдером или неявными defaults

### Независимые явные загрузки

- Given два разных отображения environment
- When каждое по очереди передаётся в `load_config`
- Then создаются два независимых `Config` с соответствующими подконфигами
- And первая конфигурация не изменяется после второй загрузки
- And модуль не сохраняет ни один объект как глобальное состояние

## Технологии и структура

- Python 3.12, Pydantic и стандартные `os`/`collections.abc` остаются
  единственными средствами загрузки и валидации конфигурации.
- Общая точка входа остаётся в
  `backend/src/smeshariki_ai/config.py` и экспортирует только корневой `Config`
  и `load_config` как backend-wide contract.
- `AgentConfig` продолжает находиться в `smeshariki_ai.agent`, а
  `LiteLLMProviderConfig` — в `smeshariki_ai.agent.providers`. Направление
  зависимости идёт от общего composition/config слоя к component-owned
  моделям; обратного импорта корневого `Config` во внутренние компоненты нет.
- `main.py` является внешней границей ASGI-процесса и выполняет
  `create_application(load_config())`. `bootstrap.py` остаётся composition root,
  принимает готовый `Config` и не выполняет I/O конфигурации.
- Имена environment variables и файлы в `docker/` не меняются; они проверяются
  на отсутствие регрессии, но новые структурные автотесты для Compose и
  документации не добавляются.
- Создаётся тематическая страница `docs/configuration.md`; глобальная карта
  `docs/README.md` и корневой `AGENTS.md` обновляются в рамках изменения.

## Команды

- Запуск: `make run` по-прежнему загружает значения из `docker/.env` через
  Compose и передаёт их единственному backend-сервису.
- Тесты: `make test` запускает полный набор продуктовых Python-тестов через
  `uv` без сети и внешнего LLM.
- Линтинг: `make lint` проверяет Python-код backend через Ruff.
- Форматирование: `make format` исправляет и форматирует Python-код через Ruff.

## Тестирование

| Требования | Способ проверки |
| --- | --- |
| REQ-001–REQ-003 | Unit-тесты структуры и неизменяемости корневого значения через его публичные поля; ревью направления импортов без отдельного теста дерева файлов |
| REQ-004–REQ-008 | Unit-тесты `load_config` с явными отображениями, defaults, полным набором переменных, blank optional values, ошибками, повторными независимыми загрузками и маркерами process environment |
| REQ-009–REQ-012 | Unit-тесты entrypoint и bootstrap с monkeypatch-конструкторами: один вызов loader, отсутствие скрытого loader в `create_application`, передача тех же экземпляров подконфигов и явная provider-подмена |
| REQ-013–REQ-015 | Ревью импортов, environment reads, dependency tree и Docker diff; отдельные структурные тесты не добавляются |
| REQ-016 | Ревью `docs/configuration.md`, `docs/README.md` и `AGENTS.md` без автоматических тестов документации |
| REQ-017 | Запуск `make test` и `make lint` из корня репозитория |

Тесты проверяют наблюдаемую загрузку и передачу конфигурации, а не наличие
конкретных private helper-функций или физическую структуру каталога. Все тесты
используют fake/mocked provider и не выполняют внешний LLM-запрос.

## Границы

- Всегда: иметь один публичный `load_config`; возвращать immutable `Config` с
  component-owned подконфигами; загружать конфигурацию на внешней границе;
  передавать компоненту только его подконфиг; сохранять текущий environment и
  Docker contract; скрывать секреты.
- Сначала спросить: переименовать environment variables; добавить новый
  подконфиг или источник конфигурации; подключить `pydantic-settings`, YAML,
  secrets manager или файловый `.env` loader; превратить `smeshariki_ai.config`
  в package; настроить reload конфигурации во время работы.
- Никогда: создавать module-level `Config` singleton; читать environment внутри
  agent/provider/API/application/dialogs; передавать весь `Config` в доменный
  компонент; дублировать поля component config в корневой модели; создавать
  конфиги ещё не реализованных компонентов; логировать secrets; добавлять
  структурные тесты только ради файлов или документации.

## Критерии приёмки

- [ ] `from smeshariki_ai.config import Config, load_config` предоставляет
  единственный корневой тип и loader backend; `ApplicationConfig` отсутствует.
- [ ] `Config` immutable, запрещает extra fields и содержит только `agent` и
  `llm` с действующими component-owned типами.
- [ ] Все текущие `AGENT_*` и `LLM_*` значения загружаются в соответствующие
  вложенные подконфиги с прежними defaults, обязательностью и валидацией.
- [ ] Только `smeshariki_ai.config` обращается к `os.environ`; глобальный config
  singleton отсутствует.
- [ ] `main.py` загружает `Config` один раз, а `create_application` и остальной
  bootstrap не имеют скрытого чтения environment.
- [ ] `Agent` получает непосредственно `config.agent`, `LiteLLMProvider` —
  `config.llm`; внутренние компоненты не знают о корневом `Config`.
- [ ] Явная fake-подмена работает только с валидным переданным `Config` и не
  становится production fallback.
- [ ] Docker/environment, HTTP, agent loop и LLM-provider behavior не изменены.
- [ ] Новые runtime-зависимости отсутствуют; `uv.lock` не меняется из-за этой
  спецификации.
- [ ] `docs/configuration.md`, `docs/README.md` и `AGENTS.md` описывают
  реализованный поток конфигурации и архитектурные границы.
- [ ] `make test` и `make lint` проходят успешно без сети и реального LLM.

## Открытые вопросы

- Нет. Корневой тип называется `Config`; физически общий модуль остаётся
  `smeshariki_ai/config.py`, а текущие environment variables сохраняются.
