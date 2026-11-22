# Агент

[← Глобальный каталог](./README.md)

Agent runtime — внутренняя часть backend, независимая от HTTP и хранения
диалогов. Он выполняет ограниченный tool-calling loop и получает все
инфраструктурные зависимости снаружи.

## Где находится реализация

- [`agent/runtime.py`](../backend/src/smeshariki_ai/agent/runtime.py) — цикл и
  класс `Agent`;
- [`agent/providers/`](../backend/src/smeshariki_ai/agent/providers/) —
  абстракция `LLMProvider`, `FakeLLMProvider`, production-адаптер LiteLLM и его
  отдельная конфигурация;
- [`agent/tools.py`](../backend/src/smeshariki_ai/agent/tools.py) — `Tool` и
  `ToolRegistry`;
- [`agent/models.py`](../backend/src/smeshariki_ai/agent/models.py) —
  неизменяемые Pydantic-модели сообщений, вызовов и ответов.
- [`agent/prompts/system.md`](../backend/src/smeshariki_ai/agent/prompts/system.md)
  — версионируемый production-системный промпт; соседний Python-модуль
  загружает его как package resource.

## Внутренние контракты

```python
Agent(
    llm_provider: LLMProvider,
    tool_registry: ToolRegistry,
    config: AgentConfig,
)

Agent.run(
    history: Sequence[Message],
    request: UserRequest,
) -> AsyncIterator[AgentTextDelta | AgentResponse]
```

`Agent.run` не изменяет переданную историю. Для запуска он формирует рабочий
контекст из системного сообщения, снимка истории и нового пользовательского
запроса. Если в `UserRequest` задано `reading_minutes` (2, 5 или 10), сразу
после основного промпта добавляется второе системное сообщение «Объём ответа:
история примерно на N минут чтения — около W слов.» (`W = N × 150`). Оно, как и
внутренние сообщения о вызовах инструментов, существует только в этом
контексте и в историю диалога не попадает. Для той же длительности `Agent`
передаёт провайдеру `max_tokens`: `2` минуты — `1200`, `5` — `3000`, `10` —
`6000`; без выбранной длительности лимит не передаётся. `Agent.run` является
единственным путём выполнения: он передаёт фрагменты только финального текста,
а затем полный `AgentResponse`.

Runtime не читает Markdown-файл или environment. Общий
[`load_config`](./configuration.md) загружает production-промпт через
`importlib.resources` при старте и передаёт готовый текст в неизменяемом
`AgentConfig`. Поэтому изменение промпта проходит обычное Git-review и входит
в Python-дистрибутив. Промпт требует писать только готовый русский текст без
Markdown, иероглифов, служебных пометок и упоминаний инструментов; deployment
override через environment не поддерживается.

```python
LLMProvider.stream(
    messages: Sequence[Message],
    tools: Sequence[ToolDefinition],
    max_tokens: int | None = None,
) -> AsyncIterator[LLMTextDelta | LLMResponse]
```

Провайдер получает контекст и определения доступных инструментов на каждой
итерации. Типы SDK конкретного поставщика не входят во внутренний контракт.
Текстовые delta завершаются ровно одним доменным `LLMResponse`; непотокового
метода генерации на уровне провайдера нет.
Штатная сборка использует `LiteLLMProvider`, а `FakeLLMProvider` сохраняется для
детерминированных тестов и явной подмены зависимости.

```python
LiteLLMProvider(
    config=LiteLLMProviderConfig(
        model="provider/model",
        api_key=None,
        base_url=None,
        timeout_seconds=60,
        num_retries=0,
        temperature=0.8,
        thinking=False,
    )
)
```

`LiteLLMProviderConfig` неизменяем и содержит только настройки провайдера.
Общий [`load_config`](./configuration.md) читает environment на внешней границе;
сам адаптер получает готовый объект и не загружает `.env`.
Production-конфигурация требует `LLM_MODEL`, а необязательные `LLM_API_KEY` и
`LLM_BASE_URL` зависят от выбранного через LiteLLM поставщика. `LLM_TEMPERATURE`
задаёт температуру генерации (`0…2`, по умолчанию `0.8`), а `LLM_THINKING`
включает скрытые рассуждения DeepSeek (по умолчанию выключены). Для
не-DeepSeek модели `LLM_THINKING=true` отклоняется при загрузке конфигурации.

```python
class Tool(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    arguments_model: ClassVar[type[BaseModel]]

    async def execute(self, arguments: BaseModel) -> Any: ...

ToolRegistry(tools: Sequence[Tool])
await ToolRegistry.execute(tool_call: ToolCall) -> ToolResult
```

Каждый инструмент наследуется от `Tool` и объявляет Pydantic-модель аргументов.
`ToolRegistry` принимает последовательность экземпляров, запрещает повторяющиеся
имена, строит JSON Schema для LLM и является единственной точкой выполнения
tool call. Неизвестное имя, невалидные аргументы и ошибка исполнения
преобразуются в безопасный `ToolResult`.

Production bootstrap регистрирует в `ToolRegistry` только
`lookup_knowledge`. Когда вызывать инструмент, модель узнаёт из его описания;
решение о вызове остаётся за моделью. Результаты поиска передаются как данные и
не становятся частью системного промпта.

## Правила agent loop

- стандартный лимит — четыре итерации, значение задаётся через `AgentConfig`;
- один `LLMResponse` содержит либо финальный `content`, либо один или
  несколько tool calls;
- пустая строка `content=""` является успешным финальным ответом;
- одновременный текст и tool calls либо отсутствие обоих вариантов считаются
  некорректным ответом провайдера;
- вызовы одного ответа выполняются последовательно в порядке модели; первые
  `AgentConfig.max_tool_calls_per_response` (по умолчанию 4) — через
  `ToolRegistry`, остальные получают `ToolResult` с ошибкой
  `tool_call_limit_exceeded`;
- после вызовов в рабочий контекст добавляются одно сообщение ассистента со
  всеми вызовами ответа и его рассуждениями (`reasoning_content`, если модель
  их прислала) и по сообщению с результатом на каждый вызов, и агент снова
  обращается к LLM;
- отсутствие финального ответа в пределах лимита завершает запуск
  контролируемой ошибкой.

`LiteLLMProvider` использует только асинхронный
`litellm.acompletion(..., stream=True)`. Он переводит доменные сообщения и
определения инструментов в Chat Completions format, передаёт `temperature`,
`max_tokens` и для DeepSeek — `thinking`, немедленно передаёт текстовые
fragments и собирает фрагментированные function calls по их `index` в доменные
`ToolCall`. При включённом thinking к явно заданному `max_tokens` добавляется
резерв `3000` токенов на скрытые рассуждения. Повторяющиеся `id`, пустые `id`
или имя и аргументы, не являющиеся JSON-объектом, делают ответ некорректным.
Фрагменты `reasoning_content` ответа с вызовами собираются отдельно и
возвращаются модели полем `reasoning_content` сообщения ассистента: модели в
режиме рассуждений (например, DeepSeek) без этого отвечают `400`. Рассуждения
финального ответа отбрасываются. Инструменты LiteLLM не выполняет: это остаётся
ответственностью agent loop. Один экземпляр адаптера не хранит состояние между
запросами и может конкурентно обслуживать независимые диалоги.

Некорректная структура внешнего ответа, невалидные JSON-аргументы tool call и
ошибки внешнего сервиса преобразуются в безопасную `LLMProviderError`.
`asyncio.CancelledError` не скрывается, чтобы shutdown мог отменить фоновый
запуск. `FakeLLMProvider` по-прежнему не использует сеть и возвращает успешный
пустой финальный ответ.

## Наблюдаемость

Runtime журналирует начало запуска, каждую итерацию, тип ответа LLM и число
вызовов в нём (`tool_call_count`), имя и статус каждого инструмента со своим
`tool_call_id`, успешное завершение и тип ошибки. Текст запроса и истории,
аргументы и результаты инструмента, рассуждения модели, финальный ответ и текст
исключения в лог не передаются.

LiteLLM-адаптер отдельно журналирует начало, завершение и ошибку внешнего
запроса с model, количеством сообщений и инструментов и безопасным типом
ошибки. API key, base URL, содержимое сообщений, tool payload, ответ модели и
текст внешнего исключения не журналируются; callbacks LiteLLM не подключаются.

## Где искать подробности

- [спецификация](../specs/changes/agent-runtime/spec.md);
- [план](../specs/changes/agent-runtime/plan.md);
- [результат проверки](../specs/changes/agent-runtime/verification.md);
- [спецификация LiteLLM-провайдера](../specs/changes/litellm-provider/spec.md);
- [план LiteLLM-провайдера](../specs/changes/litellm-provider/plan.md);
- [результат проверки LiteLLM-провайдера](../specs/changes/litellm-provider/verification.md);
- [спецификация resource системного промпта](../specs/changes/agent-system-prompt-resource/spec.md);
- [план resource системного промпта](../specs/changes/agent-system-prompt-resource/plan.md);
- [результат проверки resource системного промпта](../specs/changes/agent-system-prompt-resource/verification.md);
- [спецификация streaming и SSE](../specs/changes/agent-sse-test-ui/spec.md);
- [план streaming и SSE](../specs/changes/agent-sse-test-ui/plan.md);
- [результат проверки streaming и SSE](../specs/changes/agent-sse-test-ui/verification.md);
- [спецификация нескольких вызовов в одном ответе](../specs/changes/agent-multiple-tool-calls/spec.md);
- [план нескольких вызовов в одном ответе](../specs/changes/agent-multiple-tool-calls/plan.md);
- [результат проверки нескольких вызовов в одном ответе](../specs/changes/agent-multiple-tool-calls/verification.md);
- [спецификация улучшения агента](../specs/changes/agent-improving/spec.md);
- [план улучшения агента](../specs/changes/agent-improving/plan.md);
- [результат проверки улучшения агента](../specs/changes/agent-improving/verification.md).
