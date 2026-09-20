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
запроса. Внутренние сообщения о вызовах инструментов существуют только в этом
контексте. `Agent.run` является единственным путём выполнения: он передаёт
фрагменты только финального текста, а затем полный `AgentResponse`.

Runtime не читает Markdown-файл или environment. Общий
[`load_config`](./configuration.md) загружает production-промпт через
`importlib.resources` при старте и передаёт готовый текст в неизменяемом
`AgentConfig`. Поэтому изменение промпта проходит обычное Git-review и входит
в Python-дистрибутив, а deployment override через `AGENT_SYSTEM_PROMPT` не
поддерживается.

```python
LLMProvider.stream(
    messages: Sequence[Message],
    tools: Sequence[ToolDefinition],
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
    )
)
```

`LiteLLMProviderConfig` неизменяем и содержит только настройки провайдера.
Общий [`load_config`](./configuration.md) читает environment на внешней границе;
сам адаптер получает готовый объект и не загружает `.env`.
Production-конфигурация требует `LLM_MODEL`, а необязательные `LLM_API_KEY` и
`LLM_BASE_URL` зависят от выбранного через LiteLLM поставщика.

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

## Правила agent loop

- стандартный лимит — четыре итерации, значение задаётся через `AgentConfig`;
- один `LLMResponse` содержит либо финальный `content`, либо ровно один tool
  call;
- пустая строка `content=""` является успешным финальным ответом;
- несколько tool calls, одновременный текст и tool call либо отсутствие обоих
  вариантов считаются некорректным ответом провайдера;
- после tool call результат добавляется в рабочий контекст, и агент снова
  обращается к LLM;
- отсутствие финального ответа в пределах лимита завершает запуск
  контролируемой ошибкой.

`LiteLLMProvider` использует только асинхронный
`litellm.acompletion(..., stream=True)`. Он переводит доменные сообщения и
определения инструментов в Chat Completions format, немедленно передаёт
текстовые fragments и собирает фрагментированный function call в доменный
`ToolCall`. Инструменты LiteLLM не выполняет: это остаётся ответственностью
agent loop. Один экземпляр адаптера не хранит состояние между запросами и может
конкурентно обслуживать независимые диалоги.

Некорректная структура внешнего ответа, невалидные JSON-аргументы tool call и
ошибки внешнего сервиса преобразуются в безопасную `LLMProviderError`.
`asyncio.CancelledError` не скрывается, чтобы shutdown мог отменить фоновый
запуск. `FakeLLMProvider` по-прежнему не использует сеть и возвращает успешный
пустой финальный ответ.

## Наблюдаемость

Runtime журналирует начало запуска, каждую итерацию, тип ответа LLM, имя и
статус инструмента, успешное завершение и тип ошибки. Текст запроса и истории,
аргументы и результаты инструмента, финальный ответ и текст исключения в лог не
передаются.

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
- [результат проверки streaming и SSE](../specs/changes/agent-sse-test-ui/verification.md).
