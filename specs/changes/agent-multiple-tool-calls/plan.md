# План: несколько вызовов инструментов в одном ответе LLM

## Основание

План реализует согласованную спецификацию
`specs/changes/agent-multiple-tool-calls/spec.md` в ветке
`feat/agent-multiple-tool-calls` от `main`. Коммиты — только по просьбе
пользователя.

## Решения и зависимости

- `Message.tool_call` заменяется на `Message.tool_calls: tuple[ToolCall, ...]`
  (по умолчанию пустой). Поле используют только `runtime.py`,
  `providers/litellm.py` и их тесты; история диалогов и API его не читают.
- `LiteLLMProvider._map_message` для сообщения ассистента с вызовами отдаёт
  `content: None` и массив `tool_calls` в порядке кортежа.
- В потоке фрагменты копятся в `dict[int, _ToolCallParts]`; итог сортируется
  по `index`. Проверки `id`, имени, JSON-объекта и уникальности `id`
  выполняются после окончания потока. Неотрицательность индекса — при приёме
  фрагмента.
- `Agent._result_type`: `TOOL_CALL` при отсутствии текста и `len(tool_calls) >= 1`.
- Вызовы сверх лимита получают `ToolResult(call_id, name,
  error=ToolError(code="tool_call_limit_exceeded", message=...))` без
  обращения к `ToolRegistry`; для журнала — `tool_name` по правилу известного
  имени, как сейчас.
- Риск первым: что DeepSeek принимает историю с одним сообщением ассистента с
  двумя вызовами и двумя tool-сообщениями. Проверяется одним реальным
  запросом в контейнере backend в задаче 1.

## Порядок реализации

1. Сообщение ассистента с несколькими вызовами (модель, отображение в Chat
   Completions, перевод runtime на кортеж для одного вызова) и проверка
   формата на DeepSeek. Выполнена: проверка показала, что DeepSeek требует
   вернуть `reasoning_content`, — добавлена задача 2a.
2. Сборка нескольких вызовов из потока в провайдере.
2a. Возврат рассуждений модели в сообщении ассистента с вызовами.
3. Выполнение нескольких вызовов в runtime, лимит, журнал, отмена.
4. Документация.
5. Verify.

## Задача 1. Сообщение с несколькими вызовами

**Связанные требования:** REQ-006 (и подготовка REQ-004).

**Критерии приёмки:** сообщение ассистента с двумя вызовами отображается в
одно Chat Completions сообщение с массивом `tool_calls`; одиночный вызов
работает как раньше; DeepSeek принимает такую историю.

**Зависимости:** нет.

**Файлы:** `agent/models.py`, `agent/runtime.py`,
`agent/providers/litellm.py`, `tests/unit/agent/test_runtime.py`,
`tests/unit/agent/providers/test_litellm.py`.

**Шаги:** RED — тест отображения сообщения с двумя вызовами в
`test_litellm.py` падает; GREEN — `Message.tool_calls`, `_map_message`,
runtime создаёт сообщение с кортежем из одного вызова; обновить существующие
утверждения `tool_call` → `tool_calls`.

**Проверка:** `uv run --project backend --locked pytest backend/tests/unit/agent`;
один реальный запрос в контейнере backend с историей «ассистент: два вызова →
два результата».

## Задача 2. Сборка нескольких вызовов в провайдере

**Связанные требования:** REQ-001, REQ-002.

**Критерии приёмки:** два и три вызова с перемешанными фрагментами
собираются в порядке `index`; повторный `id`, пустое имя или `id`, не-JSON и
не-объект аргументы, текст вместе с вызовами, отрицательный индекс —
`LLMProviderError`.

**Зависимости:** задача 1.

**Файлы:** `agent/providers/litellm.py`,
`tests/unit/agent/providers/test_litellm.py`.

**Шаги:** RED — тесты нескольких вызовов и новых некорректных случаев;
GREEN — убрать ограничение `index == 0`, собрать и проверить все вызовы;
REFACTOR — вынести сборку итоговых `ToolCall` в отдельную функцию.

**Проверка:** `uv run --project backend --locked pytest backend/tests/unit/agent/providers`.

## Задача 2a. Возврат рассуждений модели

**Связанные требования:** REQ-010, REQ-011.

**Критерии приёмки:** фрагменты `delta.reasoning_content` ответа с вызовами
собираются в `LLMResponse.reasoning_content` и не выдаются как
`LLMTextDelta`; нестроковое значение — `LLMProviderError`; сообщение
ассистента с вызовами передаёт `reasoning_content` только непустым; `Agent`
переносит рассуждения в сообщение ассистента, а в финальный ответ и историю
они не попадают; журнал их не содержит.

**Зависимости:** задачи 1 и 2.

**Файлы:** `agent/models.py`, `agent/providers/litellm.py`,
`agent/runtime.py`, `tests/unit/agent/providers/test_litellm.py`,
`tests/unit/agent/test_runtime.py`.

**Шаги:** RED — тесты сборки, отображения и переноса рассуждений; GREEN —
поле `reasoning_content` в `LLMResponse` и `Message`, сбор в потоке,
отображение, перенос в runtime.

**Проверка:** `uv run --project backend --locked pytest backend/tests/unit/agent`;
реальный запрос в контейнере backend после пересборки: ход с вызовом и его
продолжение проходят без `400`.

## Задача 3. Выполнение нескольких вызовов в runtime

**Связанные требования:** REQ-003, REQ-004, REQ-005, REQ-007, REQ-008.

**Критерии приёмки:** ответ с двумя вызовами даёт в контексте следующего
обращения одно сообщение ассистента и два результата по порядку; лимит 2 при
трёх вызовах — третий не выполнен и получил `tool_call_limit_exceeded`;
`AgentConfig.max_tool_calls_per_response` отвергает значения ≤ 0;
`agent.llm.completed` содержит `tool_call_count`, события `agent.tool.*`
пишутся по каждому вызову без payload; отмена во время второго вызова
распространяется; тест `multiple-tools` в `test_invalid_llm_response_is_rejected`
заменяется положительным сценарием.

**Зависимости:** задача 1.

**Файлы:** `agent/models.py`, `agent/runtime.py`,
`tests/unit/agent/test_runtime.py`.

**Шаги:** RED — тесты сценариев выше; GREEN — `_result_type`, цикл по
вызовам с лимитом, поле журнала; REFACTOR — вынести выполнение одного вызова
с журналом в отдельный метод.

**Проверка:** `uv run --project backend --locked pytest backend/tests/unit/agent`.

## Задача 4. Документация

**Связанные требования:** REQ-009.

**Критерии приёмки:** `docs/agent.md` («Правила agent loop», описание
`LiteLLMProvider`, «Наблюдаемость», ссылки на SDD) и пункт 2 раздела
«Реализованный runtime агента» в `AGENTS.md` описывают несколько вызовов и
лимит.

**Зависимости:** задачи 2 и 3.

**Файлы:** `docs/agent.md`, `AGENTS.md`.

**Проверка:** ревью.

## Задача 5. Verify

**Связанные требования:** все.

**Критерии приёмки:** все критерии спецификации подтверждены;
`verification.md` записан.

**Зависимости:** задачи 1–4.

**Файлы:** `specs/changes/agent-multiple-tool-calls/verification.md`.

**Проверка:** `make lint`; `make test`; пересборка `make run` и запрос
«Придумай мне сказку про Кроша и Ежика с их любимыми предметами» в чате:
финальный ответ, в журнале `tool_call_count=2` и два `rag.lookup.completed`.
