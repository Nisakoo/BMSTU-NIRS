# План: LiteLLM-провайдер и подмодуль LLM-провайдеров
Исторический план. Полная версия: `git show 5af56b5:specs/changes/litellm-provider/plan.md`.

## Основание
План реализует одобренную спецификацию [`spec.md`](./spec.md) поверх готовых изменений `agent-runtime` и `agent-dialog-api`. Результат заменит штатный `FakeLLMProvider` в composition root на реальный
асинхронный `LiteLLMProvider`, но сохранит fake-реализацию для тестов и явной подмены зависимости.
До начала планирования исходная ветка проверена командами `make test` и `make lint`: проходят 54 теста, Ruff не находит нарушений. Это базовая точка, относительно которой будет проверяться реализация.

## Решения и зависимости

### Версия LiteLLM и способ интеграции
На 19 сентября 2026 года актуальный стабильный релиз LiteLLM — `1.101.0`. В `backend/pyproject.toml` добавляется диапазон `litellm>=1.101.0,<2`, а точное разрешение вместе с транзитивными
зависимостями фиксируется `backend/uv.lock`. Pre-release версии не используются.
Адаптер вызывает только `litellm.acompletion` с `stream=False`. Официальный Chat Completions-контракт LiteLLM принимает `messages`, function `tools`, `timeout`, `base_url`, `api_key` и `num_retries`;
синхронный `completion`, Responses API, Router и Proxy не используются:

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
`agent.models` остаётся владельцем `Message`, `LLMResponse`, `ToolCall` и `ToolDefinition`. После миграции `agent/llm.py` удаляется, а поддерживаемые импорты продолжают работать через фасад `smeshariki_ai.agent`.

### Конфигурация и composition root
`LiteLLMProviderConfig` — frozen Pydantic-модель с `extra="forbid"`:

- `model: str` — обязательная непустая строка;
- `api_key: SecretStr | None = None`;
- `base_url: AnyHttpUrl | None = None`;
- `timeout_seconds: float = 60`, строго больше нуля;
- `num_retries: int = 0`, не меньше нуля.
`ApplicationConfig` содержит эту модель отдельным полем `llm_provider`, рядом с существующими настройками агента, но не смешивает их. `load_config` является единственным местом чтения `LLM_*`
environment variables. Пустые необязательные строки нормализуются в `None`; `LLM_MODEL` без default обязателен.
`build_agent_service` и `create_application` получают необязательную явную подмену `llm_provider` для тестов. Если подмена не передана, composition root всегда создаёт
`LiteLLMProvider(config.llm_provider)`. Это тестовый seam, а не fallback: ошибка или отсутствие production-конфигурации никогда не включает `FakeLLMProvider` автоматически.

### Преобразование запроса
Адаптер строит новые локальные словари на каждый вызов и не хранит состояние конкретного запроса в экземпляре:

- обычные `system`, `user` и `assistant` передаются с исходным `content`;
- `assistant` с `ToolCall` становится function tool call с JSON-строкой аргументов и `content=None`;
- `tool` содержит `tool_call_id` и JSON-представление всего `ToolResult`;
- `ToolDefinition` становится `{"type": "function", "function": ...}`;
- аргументы JSON сериализуются детерминированно; tools полностью опускаются из вызова, если реестр пуст;
- `api_key` раскрывается из `SecretStr` только при формировании kwargs вызова; необязательные `None`-параметры в LiteLLM не передаются.
LiteLLM не получает callbacks, MCP tools или настройку автоматического исполнения functions. `ToolRegistry` остаётся единственным исполнителем.

### Преобразование ответа и ошибок
Из первого choice непотокового `ModelResponse` читаются `content` и все `tool_calls`. `None` и пустая строка сохраняются различными значениями. Аргументы каждого function call разбираются `json.loads`
и принимаются только как объект; несколько calls и смешанный text/tool ответ намеренно доходят до существующей проверки `Agent` без фильтрации.
Пустой choices, несовместимые поля, невалидный JSON, JSON не в форме объекта и ошибка сериализации `ToolResult` превращаются в `LLMProviderError` с фиксированным безопасным сообщением. Все обычные
исключения `litellm.acompletion` также оборачиваются в `LLMProviderError`; `asyncio.CancelledError` не перехватывается. Исходная ошибка может быть сохранена только как exception cause и не попадает в
сообщение или журнал.
Провайдер журналирует стабильные события `llm.request.started`, `llm.request.completed` и `llm.request.failed` с model, количеством сообщений и tools и безопасным `error_type`. Verbose mode и
callbacks LiteLLM не включаются. В лог не передаются kwargs, содержимое, tool payload, ответ, credentials, base URL и текст исключения.

### Асинхронность и конкурентность
`generate` непосредственно делает `await litellm.acompletion(...)`: не вызывает `litellm.completion`, не использует `asyncio.to_thread` и не создаёт глобальный lock. Один экземпляр хранит только
immutable config, поэтому два независимых диалога могут ожидать два вызова одновременно. Управляемый async-double в тесте заблокирует первый вызов и докажет, что второй стартует и завершается до его
освобождения.

## Порядок реализации

1. Добавить и зафиксировать LiteLLM dependency.
2. Создать пакет провайдеров, перенести базовый контракт и ввести отдельную конфигурацию.
3. Через TDD реализовать исходящее преобразование Chat Completions.
4. Через TDD реализовать ответы, безопасные ошибки, логи и конкурентность.
5. Переключить agent runtime и публичный фасад на новый подмодуль, удалить старый `agent.llm`.
6. Подключить production-провайдер в конфигурации и bootstrap, проверить фоновый HTTP-сбой.
7. Обновить Docker environment contract и руководство запуска.
8. Обновить архитектурный каталог и корневые правила.
9. Выполнить полную проверку реализации перед этапом `verify`.
Задачи 1–4 закрывают наиболее рискованные предположения — совместимость SDK, точный wire format, ошибки и настоящую асинхронность — до подключения адаптера к штатному приложению.

## Задача 1. Добавить LiteLLM dependency
**Связанные требования:** REQ-018, REQ-022.
**Критерии приёмки:** стабильный LiteLLM доступен backend на Python 3.12; lock-файл воспроизводим; существующий набор тестов остаётся зелёным; LangChain и LangGraph не появляются.
**Зависимости:** нет.
**Проверка:**

```sh
uv lock --project backend --check
uv run --project backend --locked python -c "from importlib.metadata import version; print(version('litellm'))"
make test

```

## Задача 2. Создать границу провайдеров и конфигурацию
**Связанные требования:** REQ-001–REQ-005, REQ-021.
**Критерии приёмки:** контракт, fake, ошибка и provider-only config доступны из `agent.providers`; конфигурация immutable, запрещает лишние и невалидные поля и скрывает API key; существующий runtime
временно продолжает работать через тонкий re-export из `agent.llm` до окончательной миграции задачи 5.
**Зависимости:** задача 1.
**Тест:**

```sh
uv run --project backend --locked pytest backend/tests/unit/agent/test_llm.py backend/tests/unit/agent/providers/test_config.py

```

## Задача 3. Реализовать асинхронное формирование LiteLLM-запроса
**Связанные требования:** REQ-004, REQ-008–REQ-011.
**Критерии приёмки:** `LiteLLMProvider` получает config через конструктор, вызывает именно `litellm.acompletion` и корректно преобразует все доменные роли, tool definitions и tool results, не изменяя входные объекты и не выполняя tools.
**Зависимости:** задача 2.
**Тест:**

```sh
uv run --project backend --locked pytest backend/tests/unit/agent/providers/test_litellm.py -k "request or message or tool_definition or tool_result"

```

## Задача 4. Преобразовать ответы, ошибки и доказать конкурентность
**Связанные требования:** REQ-012–REQ-016, REQ-023.
**Критерии приёмки:** provider сохраняет `None`/`""`, переводит все function calls, отдаёт неоднозначные ответы на проверку `Agent`, безопасно оборачивает ошибки, не перехватывает cancellation и
допускает одновременный прогресс двух вызовов без смешивания состояния.
**Зависимости:** задача 3.
**Тест:**

```sh
uv run --project backend --locked pytest backend/tests/unit/agent/providers/test_litellm.py

```

## Задача 5. Завершить миграцию импортов и удалить `agent.llm`
**Связанные требования:** REQ-001–REQ-003, REQ-013, REQ-021.
**Критерии приёмки:** runtime зависит от нового provider contract; импорты из `smeshariki_ai.agent` обратно совместимы; старого внутреннего модуля и ссылок на него нет; поведение существующего agent loop не изменилось.
**Зависимости:** задачи 2–4.
**Тест:**

```sh
uv run --project backend --locked pytest backend/tests/unit/agent
uv run --project backend --locked python -c "from smeshariki_ai.agent import FakeLLMProvider, LiteLLMProvider, LiteLLMProviderConfig, LLMProvider, LLMProviderError"

```

## Задача 6. Подключить конфигурацию, bootstrap и фоновый HTTP-сбой
**Связанные требования:** REQ-006, REQ-007, REQ-015–REQ-017, REQ-022.
**Критерии приёмки:** environment собирает отдельный provider config; штатный bootstrap использует LiteLLM; явная тестовая подмена не является fallback; невалидный startup config отклоняется; ошибка
адаптера после HTTP `202` не изменяет историю и логируется безопасно.
**Зависимости:** задача 5.
**Тест:**

```sh
uv run --project backend --locked pytest backend/tests/unit/test_bootstrap.py backend/tests/integration/api/test_litellm_provider.py

```

## Задача 7. Обновить Docker-конфигурацию запуска
**Связанные требования:** REQ-006, REQ-019.
**Критерии приёмки:** Compose передаёт только согласованные `LLM_*` настройки в backend, требует model, не содержит секрета или LiteLLM-сервиса и по-прежнему не включает frontend; руководство объясняет локальную настройку.
**Зависимости:** задача 6.
**Проверка ревью:**

```sh
docker compose --env-file docker/.env.example -f docker/compose.yaml config
docker compose --env-file docker/.env.example -f docker/compose.yaml config --services

```
Отдельный автотест структуры Compose или `.env.example` не добавляется.

## Задача 8. Актуализировать архитектуру и контракты
**Связанные требования:** REQ-019, REQ-020.
**Критерии приёмки:** документация описывает фактический provider submodule, асинхронный DI-контракт, production LiteLLM adapter, environment boundary и ограничения; глобальная карта больше не показывает fake как штатный provider.
**Зависимости:** задачи 5–7.
**Проверка ревью:**

```sh
sed -n '1,260p' docs/agent.md
sed -n '1,260p' docs/README.md
sed -n '80,170p' AGENTS.md

```
Документация и Mermaid проверяются ревью, без искусственных автотестов.

## Итоговая проверка реализации
**Связанные требования:** REQ-001–REQ-023 и все критерии приёмки.

1. Запустить полный продуктовый набор тестов и Ruff из корня: ```sh make test make lint ```
2. Проверить lock-файл и импорт production API: ```sh uv lock --project backend --check uv run --project backend --locked python -c "from smeshariki_ai.agent import LiteLLMProvider, LiteLLMProviderConfig, LLMProviderError" ```
3. Просмотреть дерево зависимостей и подтвердить наличие LiteLLM и отсутствие LangChain/LangGraph: ```sh uv tree --project backend ```
4. Проверить итоговый Compose через `.env.example` и убедиться, что единственный сервис — backend.
5. Поискать оставшиеся ссылки на `smeshariki_ai.agent.llm`, синхронный `litellm.completion`, `asyncio.to_thread`, реальные credentials и пользовательские payload в логировании.
6. Сопоставить каждый REQ и критерий спецификации с тестом либо результатом ревью. Реальный сетевой вызов LLM не входит в обязательную проверку.
7. После реализации перейти к отдельному этапу `verify`, создать `verification.md` и только после успешного verify установить статус `done`.
