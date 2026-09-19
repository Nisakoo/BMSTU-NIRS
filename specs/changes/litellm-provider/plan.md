# План: LiteLLM-провайдер и подмодуль LLM-провайдеров

## Основание

План реализует одобренную спецификацию
[`spec.md`](./spec.md) поверх готовых изменений `agent-runtime` и
`agent-dialog-api`. Результат заменит штатный `FakeLLMProvider` в composition
root на реальный асинхронный `LiteLLMProvider`, но сохранит fake-реализацию для
тестов и явной подмены зависимости.

До начала планирования исходная ветка проверена командами `make test` и
`make lint`: проходят 54 теста, Ruff не находит нарушений. Это базовая точка,
относительно которой будет проверяться реализация.

## Решения и зависимости

### Версия LiteLLM и способ интеграции

На 19 сентября 2026 года актуальный стабильный релиз LiteLLM — `1.101.0`.
В `backend/pyproject.toml` добавляется диапазон `litellm>=1.101.0,<2`, а точное
разрешение вместе с транзитивными зависимостями фиксируется `backend/uv.lock`.
Pre-release версии не используются.

Адаптер вызывает только `litellm.acompletion` с `stream=False`. Официальный
Chat Completions-контракт LiteLLM принимает `messages`, function `tools`,
`timeout`, `base_url`, `api_key` и `num_retries`; синхронный `completion`,
Responses API, Router и Proxy не используются:

- <https://docs.litellm.ai/docs/completion/input>;
- <https://docs.litellm.ai/docs/completion/function_call>;
- <https://docs.litellm.ai/docs/exception_mapping>.

### Структура подмодуля

Целевая структура минимальна и не дробит один адаптер на лишние слои:

```text
smeshariki_ai/agent/providers/
├── __init__.py      # внутренний публичный фасад провайдеров
├── base.py          # LLMProvider, FakeLLMProvider, LLMProviderError
├── config.py        # LiteLLMProviderConfig
└── litellm.py       # LiteLLMProvider и преобразование форматов
```

`agent.models` остаётся владельцем `Message`, `LLMResponse`, `ToolCall` и
`ToolDefinition`. После миграции `agent/llm.py` удаляется, а поддерживаемые
импорты продолжают работать через фасад `smeshariki_ai.agent`.

### Конфигурация и composition root

`LiteLLMProviderConfig` — frozen Pydantic-модель с `extra="forbid"`:

- `model: str` — обязательная непустая строка;
- `api_key: SecretStr | None = None`;
- `base_url: AnyHttpUrl | None = None`;
- `timeout_seconds: float = 60`, строго больше нуля;
- `num_retries: int = 0`, не меньше нуля.

`ApplicationConfig` содержит эту модель отдельным полем `llm_provider`, рядом с
существующими настройками агента, но не смешивает их. `load_config` является
единственным местом чтения `LLM_*` environment variables. Пустые необязательные
строки нормализуются в `None`; `LLM_MODEL` без default обязателен.

`build_agent_service` и `create_application` получают необязательную явную
подмену `llm_provider` для тестов. Если подмена не передана, composition root
всегда создаёт `LiteLLMProvider(config.llm_provider)`. Это тестовый seam, а не
fallback: ошибка или отсутствие production-конфигурации никогда не включает
`FakeLLMProvider` автоматически.

### Преобразование запроса

Адаптер строит новые локальные словари на каждый вызов и не хранит состояние
конкретного запроса в экземпляре:

- обычные `system`, `user` и `assistant` передаются с исходным `content`;
- `assistant` с `ToolCall` становится function tool call с JSON-строкой
  аргументов и `content=None`;
- `tool` содержит `tool_call_id` и JSON-представление всего `ToolResult`;
- `ToolDefinition` становится `{"type": "function", "function": ...}`;
- аргументы JSON сериализуются детерминированно; tools полностью опускаются из
  вызова, если реестр пуст;
- `api_key` раскрывается из `SecretStr` только при формировании kwargs вызова;
  необязательные `None`-параметры в LiteLLM не передаются.

LiteLLM не получает callbacks, MCP tools или настройку автоматического
исполнения functions. `ToolRegistry` остаётся единственным исполнителем.

### Преобразование ответа и ошибок

Из первого choice непотокового `ModelResponse` читаются `content` и все
`tool_calls`. `None` и пустая строка сохраняются различными значениями.
Аргументы каждого function call разбираются `json.loads` и принимаются только
как объект; несколько calls и смешанный text/tool ответ намеренно доходят до
существующей проверки `Agent` без фильтрации.

Пустой choices, несовместимые поля, невалидный JSON, JSON не в форме объекта и
ошибка сериализации `ToolResult` превращаются в `LLMProviderError` с фиксированным
безопасным сообщением. Все обычные исключения `litellm.acompletion` также
оборачиваются в `LLMProviderError`; `asyncio.CancelledError` не перехватывается.
Исходная ошибка может быть сохранена только как exception cause и не попадает в
сообщение или журнал.

Провайдер журналирует стабильные события `llm.request.started`,
`llm.request.completed` и `llm.request.failed` с model, количеством сообщений и
tools и безопасным `error_type`. Verbose mode и callbacks LiteLLM не
включаются. В лог не передаются kwargs, содержимое, tool payload, ответ,
credentials, base URL и текст исключения.

### Асинхронность и конкурентность

`generate` непосредственно делает `await litellm.acompletion(...)`: не вызывает
`litellm.completion`, не использует `asyncio.to_thread` и не создаёт глобальный
lock. Один экземпляр хранит только immutable config, поэтому два независимых
диалога могут ожидать два вызова одновременно. Управляемый async-double в тесте
заблокирует первый вызов и докажет, что второй стартует и завершается до его
освобождения.

## Порядок реализации

1. Добавить и зафиксировать LiteLLM dependency.
2. Создать пакет провайдеров, перенести базовый контракт и ввести отдельную
   конфигурацию.
3. Через TDD реализовать исходящее преобразование Chat Completions.
4. Через TDD реализовать ответы, безопасные ошибки, логи и конкурентность.
5. Переключить agent runtime и публичный фасад на новый подмодуль, удалить
   старый `agent.llm`.
6. Подключить production-провайдер в конфигурации и bootstrap, проверить
   фоновый HTTP-сбой.
7. Обновить Docker environment contract и руководство запуска.
8. Обновить архитектурный каталог и корневые правила.
9. Выполнить полную проверку реализации перед этапом `verify`.

Задачи 1–4 закрывают наиболее рискованные предположения — совместимость SDK,
точный wire format, ошибки и настоящую асинхронность — до подключения адаптера
к штатному приложению.

## Задача 1. Добавить LiteLLM dependency

**Связанные требования:** REQ-018, REQ-022.

**Критерии приёмки:** стабильный LiteLLM доступен backend на Python 3.12;
lock-файл воспроизводим; существующий набор тестов остаётся зелёным; LangChain и
LangGraph не появляются.

**Зависимости:** нет.

**Файлы:**

- `backend/pyproject.toml`;
- `backend/uv.lock`.

**Действия:**

1. Добавить `litellm>=1.101.0,<2` только через `uv add --project backend`.
2. Обновить lock-файл через uv, не используя pip или ручное редактирование.
3. Проверить разрешённую версию и дерево транзитивных зависимостей.
4. Убедиться, что `langchain` и `langgraph` не добавлены.

**Проверка:**

```sh
uv lock --project backend --check
uv run --project backend --locked python -c "from importlib.metadata import version; print(version('litellm'))"
make test
```

## Задача 2. Создать границу провайдеров и конфигурацию

**Связанные требования:** REQ-001–REQ-005, REQ-021.

**Критерии приёмки:** контракт, fake, ошибка и provider-only config доступны из
`agent.providers`; конфигурация immutable, запрещает лишние и невалидные поля и
скрывает API key; существующий runtime временно продолжает работать через
тонкий re-export из `agent.llm` до окончательной миграции задачи 5.

**Зависимости:** задача 1.

**Файлы:**

- `backend/src/smeshariki_ai/agent/providers/__init__.py`;
- `backend/src/smeshariki_ai/agent/providers/base.py`;
- `backend/src/smeshariki_ai/agent/providers/config.py`;
- `backend/src/smeshariki_ai/agent/llm.py`;
- `backend/tests/unit/agent/providers/test_config.py`.

**Действия (RED → GREEN → REFACTOR):**

1. Написать падающие тесты обязательного непустого model, optional credentials,
   HTTP(S) base URL, положительного timeout, неотрицательных retries, frozen/
   extra-forbid поведения и маскирования секрета.
2. Перенести `LLMProvider` и `FakeLLMProvider` без изменения асинхронного
   доменного контракта в `providers/base.py`.
3. Добавить `LLMProviderError` как наследника `AgentError` с безопасным общим
   назначением для внешних и mapping-сбоев.
4. Реализовать `LiteLLMProviderConfig` в `providers/config.py`.
5. Собрать явный `providers/__init__.py`; на этом промежуточном шаге заменить
   содержимое `agent.llm` re-export’ом, чтобы не иметь двух определений классов.
6. Сохранить прежнее поведение `FakeLLMProvider` без сети.

**Тест:**

```sh
uv run --project backend --locked pytest backend/tests/unit/agent/test_llm.py backend/tests/unit/agent/providers/test_config.py
```

## Задача 3. Реализовать асинхронное формирование LiteLLM-запроса

**Связанные требования:** REQ-004, REQ-008–REQ-011.

**Критерии приёмки:** `LiteLLMProvider` получает config через конструктор,
вызывает именно `litellm.acompletion` и корректно преобразует все доменные роли,
tool definitions и tool results, не изменяя входные объекты и не выполняя tools.

**Зависимости:** задача 2.

**Файлы:**

- `backend/src/smeshariki_ai/agent/providers/litellm.py`;
- `backend/src/smeshariki_ai/agent/providers/__init__.py`;
- `backend/tests/unit/agent/providers/test_litellm.py`.

**Действия (RED → GREEN → REFACTOR):**

1. Подменить `litellm.acompletion` управляемой `AsyncMock`/async-функцией и
   написать падающий тест прямого запроса с model, `stream=False`, timeout,
   retries, API key и base URL.
2. Реализовать `LiteLLMProvider(config)` без чтения environment и без
   per-request полей экземпляра.
3. Добавить чистые преобразования обычных system/user/assistant messages.
4. Добавить function tool schema с сохранением name, description и parameters;
   при пустом реестре не передавать `tools`.
5. Добавить assistant tool call и связанный tool result с детерминированной
   JSON-сериализацией, включая безопасный `ToolError`.
6. Проверить, что исходные `Message`, `ToolDefinition` и config не изменяются,
   а LiteLLM auto-execution, callbacks и streaming не включены.

**Тест:**

```sh
uv run --project backend --locked pytest backend/tests/unit/agent/providers/test_litellm.py -k "request or message or tool_definition or tool_result"
```

## Задача 4. Преобразовать ответы, ошибки и доказать конкурентность

**Связанные требования:** REQ-012–REQ-016, REQ-023.

**Критерии приёмки:** provider сохраняет `None`/`""`, переводит все function
calls, отдаёт неоднозначные ответы на проверку `Agent`, безопасно оборачивает
ошибки, не перехватывает cancellation и допускает одновременный прогресс двух
вызовов без смешивания состояния.

**Зависимости:** задача 3.

**Файлы:**

- `backend/src/smeshariki_ai/agent/providers/litellm.py`;
- `backend/tests/unit/agent/providers/test_litellm.py`.

**Действия (RED → GREEN → REFACTOR):**

1. Добавить тесты обычного текста, пустой строки, `content=None`, одного,
   нескольких и смешанных tool calls.
2. Разобрать строку arguments как JSON object и создать доменные `ToolCall` без
   изменения id и name.
3. Добавить табличные тесты пустого choices, отсутствующих полей, сломанного
   JSON, JSON-массива/скаляра и несериализуемого `ToolResult`.
4. Обернуть mapping- и LiteLLM-исключения в `LLMProviderError` с фиксированным
   безопасным сообщением; отдельным тестом доказать распространение
   `asyncio.CancelledError`.
5. Добавить стабильные lifecycle logs и `caplog`-проверку с маркерами prompt,
   tool payload, ответа, key, URL и текста внешнего исключения.
6. Реализовать concurrency-тест с двумя `asyncio.Event`: первый
   `acompletion` блокируется, второй стартует и завершается до освобождения
   первого; затем проверить соответствие каждого ответа своему запросу.
7. Ревью импорта доказывает отсутствие `litellm.completion` и
   `asyncio.to_thread`; отдельный структурный автотест для исходного текста не
   добавляется.

**Тест:**

```sh
uv run --project backend --locked pytest backend/tests/unit/agent/providers/test_litellm.py
```

## Задача 5. Завершить миграцию импортов и удалить `agent.llm`

**Связанные требования:** REQ-001–REQ-003, REQ-013, REQ-021.

**Критерии приёмки:** runtime зависит от нового provider contract; импорты из
`smeshariki_ai.agent` обратно совместимы; старого внутреннего модуля и ссылок на
него нет; поведение существующего agent loop не изменилось.

**Зависимости:** задачи 2–4.

**Файлы:**

- `backend/src/smeshariki_ai/agent/llm.py` — удалить;
- `backend/src/smeshariki_ai/agent/runtime.py`;
- `backend/src/smeshariki_ai/agent/__init__.py`;
- `backend/tests/unit/agent/test_llm.py`;
- `backend/tests/unit/agent/test_runtime.py`.

**Действия (RED → GREEN → REFACTOR):**

1. Переключить `Agent` на `smeshariki_ai.agent.providers.LLMProvider`.
2. Обновить тестовые doubles и fake-тесты на новый внутренний путь либо
   поддерживаемый фасад `smeshariki_ai.agent`.
3. Экспортировать через `smeshariki_ai.agent` старые `LLMProvider` и
   `FakeLLMProvider`, а также новые `LiteLLMProvider`,
   `LiteLLMProviderConfig` и `LLMProviderError`.
4. Удалить временный re-export `agent/llm.py` и проверить отсутствие импортов
   старого пути.
5. Запустить все unit-тесты agent runtime, включая прежние проверки нескольких
   tool calls и смешанного ответа.

**Тест:**

```sh
uv run --project backend --locked pytest backend/tests/unit/agent
uv run --project backend --locked python -c "from smeshariki_ai.agent import FakeLLMProvider, LiteLLMProvider, LiteLLMProviderConfig, LLMProvider, LLMProviderError"
```

## Задача 6. Подключить конфигурацию, bootstrap и фоновый HTTP-сбой

**Связанные требования:** REQ-006, REQ-007, REQ-015–REQ-017, REQ-022.

**Критерии приёмки:** environment собирает отдельный provider config; штатный
bootstrap использует LiteLLM; явная тестовая подмена не является fallback;
невалидный startup config отклоняется; ошибка адаптера после HTTP `202` не
изменяет историю и логируется безопасно.

**Зависимости:** задача 5.

**Файлы:**

- `backend/src/smeshariki_ai/config.py`;
- `backend/src/smeshariki_ai/bootstrap.py`;
- `backend/tests/unit/test_bootstrap.py`;
- `backend/tests/integration/api/test_litellm_provider.py`.

**Действия (RED → GREEN → REFACTOR):**

1. Добавить тесты загрузки всех `LLM_*` переменных, нормализации пустых optional
   values, обязательного model и невалидных timeout/retries/base URL.
2. Вложить `LiteLLMProviderConfig` в `ApplicationConfig` без переноса
   agent-specific полей.
3. Изменить `build_agent_service` и `create_application`: по умолчанию создавать
   `LiteLLMProvider`, а в тестах принимать явно переданный `LLMProvider`.
4. Доказать unit-тестом, что отсутствие/ошибка config не создаёт приложение и
   не включает `FakeLLMProvider`.
5. Добавить интеграционный API-тест с реальным `LiteLLMProvider`, но
   подменённым `acompletion`: POST возвращает пустой `202` до фонового сбоя,
   `LLMProviderError` оставляет историю пустой, а логи содержат только
   `dialog_id` и безопасные типы ошибок.
6. Все тесты выполняются без socket и credentials.

**Тест:**

```sh
uv run --project backend --locked pytest backend/tests/unit/test_bootstrap.py backend/tests/integration/api/test_litellm_provider.py
```

## Задача 7. Обновить Docker-конфигурацию запуска

**Связанные требования:** REQ-006, REQ-019.

**Критерии приёмки:** Compose передаёт только согласованные `LLM_*` настройки в
backend, требует model, не содержит секрета или LiteLLM-сервиса и по-прежнему не
включает frontend; руководство объясняет локальную настройку.

**Зависимости:** задача 6.

**Файлы:**

- `docker/compose.yaml`;
- `docker/.env.example`;
- `docker/README.md`.

**Действия:**

1. Добавить обязательный `LLM_MODEL` и optional `LLM_API_KEY`, `LLM_BASE_URL`,
   `LLM_TIMEOUT_SECONDS`, `LLM_NUM_RETRIES` в environment backend.
2. В `.env.example` дать безопасный placeholder model, оставить API key
   закомментированным и не добавлять рабочие credentials.
3. Объяснить, что `make run` требует выбора модели, а ключ хранится только в
   ignored `docker/.env` или внешнем environment.
4. Не добавлять LiteLLM Proxy, frontend или иной сервис.

**Проверка ревью:**

```sh
docker compose --env-file docker/.env.example -f docker/compose.yaml config
docker compose --env-file docker/.env.example -f docker/compose.yaml config --services
```

Отдельный автотест структуры Compose или `.env.example` не добавляется.

## Задача 8. Актуализировать архитектуру и контракты

**Связанные требования:** REQ-019, REQ-020.

**Критерии приёмки:** документация описывает фактический provider submodule,
асинхронный DI-контракт, production LiteLLM adapter, environment boundary и
ограничения; глобальная карта больше не показывает fake как штатный provider.

**Зависимости:** задачи 5–7.

**Файлы:**

- `docs/agent.md`;
- `docs/README.md`;
- `AGENTS.md`.

**Действия:**

1. Обновить `docs/agent.md`: расположение provider package, config contract,
   async Chat Completions mapping, tool ownership, ошибки и конкурентность.
2. Обновить Mermaid-карту и состояние компонентов в `docs/README.md`; добавить
   ссылки на `litellm-provider/spec.md` и `plan.md` без копирования всей спеки.
3. В `AGENTS.md` заменить утверждения о штатном fake-bootstrap на подтверждённую
   LiteLLM-реализацию и закрепить запрет чтения environment внутри provider,
   синхронного `completion`, SDK-типов в agent runtime и сетевых unit-тестов.
4. Не объявлять реализованными SSE, RAG, streaming, Router или Proxy.

**Проверка ревью:**

```sh
sed -n '1,260p' docs/agent.md
sed -n '1,260p' docs/README.md
sed -n '80,170p' AGENTS.md
```

Документация и Mermaid проверяются ревью, без искусственных автотестов.

## Итоговая проверка реализации

**Связанные требования:** REQ-001–REQ-023 и все критерии приёмки.

1. Запустить полный продуктовый набор тестов и Ruff из корня:

   ```sh
   make test
   make lint
   ```

2. Проверить lock-файл и импорт production API:

   ```sh
   uv lock --project backend --check
   uv run --project backend --locked python -c "from smeshariki_ai.agent import LiteLLMProvider, LiteLLMProviderConfig, LLMProviderError"
   ```

3. Просмотреть дерево зависимостей и подтвердить наличие LiteLLM и отсутствие
   LangChain/LangGraph:

   ```sh
   uv tree --project backend
   ```

4. Проверить итоговый Compose через `.env.example` и убедиться, что единственный
   сервис — backend.
5. Поискать оставшиеся ссылки на `smeshariki_ai.agent.llm`, синхронный
   `litellm.completion`, `asyncio.to_thread`, реальные credentials и
   пользовательские payload в логировании.
6. Сопоставить каждый REQ и критерий спецификации с тестом либо результатом
   ревью. Реальный сетевой вызов LLM не входит в обязательную проверку.
7. После реализации перейти к отдельному этапу `verify`, создать
   `verification.md` и только после успешного verify установить статус `done`.
