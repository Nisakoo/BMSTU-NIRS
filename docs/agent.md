# Агент

[← Глобальный каталог](./README.md)

Agent runtime — внутренняя часть backend, независимая от HTTP и хранения
диалогов. Он выполняет ограниченный tool-calling loop и получает все
инфраструктурные зависимости снаружи.

## Где находится реализация

- [`agent/runtime.py`](../backend/src/smeshariki_ai/agent/runtime.py) — цикл и
  класс `Agent`;
- [`agent/llm.py`](../backend/src/smeshariki_ai/agent/llm.py) — абстракция
  `LLMProvider` и текущий `FakeLLMProvider`;
- [`agent/tools.py`](../backend/src/smeshariki_ai/agent/tools.py) — `Tool` и
  `ToolRegistry`;
- [`agent/models.py`](../backend/src/smeshariki_ai/agent/models.py) —
  неизменяемые Pydantic-модели сообщений, вызовов и ответов.

## Внутренние контракты

```python
Agent(
    llm_provider: LLMProvider,
    tool_registry: ToolRegistry,
    config: AgentConfig,
)

await Agent.run(
    history: Sequence[Message],
    request: UserRequest,
) -> AgentResponse
```

`Agent.run` не изменяет переданную историю. Для запуска он формирует рабочий
контекст из системного сообщения, снимка истории и нового пользовательского
запроса. Внутренние сообщения о вызовах инструментов существуют только в этом
контексте.

```python
await LLMProvider.generate(
    messages: Sequence[Message],
    tools: Sequence[ToolDefinition],
) -> LLMResponse
```

Провайдер получает контекст и определения доступных инструментов на каждой
итерации. Типы SDK конкретного поставщика не входят во внутренний контракт.

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

Текущий `FakeLLMProvider` не использует сеть и всегда возвращает успешный пустой
финальный ответ. Реальный провайдер и `search_knowledge` пока не реализованы.

## Наблюдаемость

Runtime журналирует начало запуска, каждую итерацию, тип ответа LLM, имя и
статус инструмента, успешное завершение и тип ошибки. Текст запроса и истории,
аргументы и результаты инструмента, финальный ответ и текст исключения в лог не
передаются.

## Где искать подробности

- [спецификация](../specs/changes/agent-runtime/spec.md);
- [план](../specs/changes/agent-runtime/plan.md);
- [результат проверки](../specs/changes/agent-runtime/verification.md).
