# План: потоковые ответы агента через SSE и тестовый интерфейс

## Контекст

Изменение переводит production-путь `LiteLLMProvider -> Agent -> AgentService`
на реальную асинхронную потоковую генерацию, добавляет in-memory broadcast
событий диалога и предоставляет их как SSE. Существующий `Agent.run` и пустой
`202 Accepted` сохраняются. Встроенная `/agent_test` использует только
публичные HTTP-ручки и браузерный `EventSource`.

Рискованные решения проверяются в первых задачах: форма LiteLLM streaming
chunks, сборка фрагментированного tool call и согласованность переданных delta с
терминальным ответом. SSE не получает replay; медленный подписчик отключается
через ограниченную очередь, не создавая backpressure для agent loop.

## Задача 1. Доменный поток LLM и детерминированный fake

**Требования:** REQ-001, REQ-004, REQ-006.

**Результат:** появляется провайдер-независимый тип текстового delta и
асинхронный контракт `LLMProvider.stream`. `generate` собирает терминальный
ответ для совместимости, а fake выдаёт корректный пустой поток без сети.

**Зависимости:** нет.

**Предполагаемые файлы:**

- `backend/src/smeshariki_ai/agent/models.py`;
- `backend/src/smeshariki_ai/agent/providers/base.py`;
- `backend/src/smeshariki_ai/agent/providers/__init__.py`;
- `backend/src/smeshariki_ai/agent/__init__.py`;
- `backend/tests/unit/agent/test_llm.py`.

**RED:** добавить тесты порядка delta/terminal response и пустого fake-ответа.

**GREEN/REFACTOR:** реализовать минимальный контракт, проверить единственный
терминальный ответ и экспортировать доменные типы.

**Проверка:**

```sh
uv run --project backend --locked pytest backend/tests/unit/agent/test_llm.py
```

## Задача 2. Потоковый LiteLLM-адаптер

**Требования:** REQ-002–REQ-005, REQ-030.

**Результат:** адаптер вызывает `acompletion(stream=True)`, передаёт текстовые
chunks немедленно, собирает tool call по index и безопасно обрабатывает
невалидные потоки, ошибки и отмену.

**Зависимости:** задача 1.

**Предполагаемые файлы:**

- `backend/src/smeshariki_ai/agent/providers/litellm.py`;
- `backend/tests/unit/agent/providers/test_litellm.py`;
- `backend/tests/integration/api/test_litellm_provider.py`.

**RED:** заменить fixtures полных ответов управляемыми async streams; добавить
проверки раннего delta, пустого ответа, фрагментированного tool call,
смешанного/повреждённого потока, безопасных логов и cancellation.

**GREEN/REFACTOR:** реализовать mapping потоковых chunks без изменяемого
состояния между запросами.

**Проверка:**

```sh
uv run --project backend --locked pytest backend/tests/unit/agent/providers/test_litellm.py backend/tests/integration/api/test_litellm_provider.py
```

## Задача 3. Потоковый agent loop с совместимым `run`

**Требования:** REQ-007–REQ-010, REQ-030.

**Результат:** `Agent.stream` выдаёт только delta финального ответа и
терминальный `AgentResponse`; tool iterations остаются внутренними. `Agent.run`
собирает этот же поток. Некорректная форма или несогласованный текст отклоняются.

**Зависимости:** задачи 1–2.

**Предполагаемые файлы:**

- `backend/src/smeshariki_ai/agent/models.py`;
- `backend/src/smeshariki_ai/agent/runtime.py`;
- `backend/src/smeshariki_ai/agent/__init__.py`;
- `backend/tests/unit/agent/test_runtime.py`.

**RED:** добавить тесты постепенной выдачи, tool call без утечки, пустого
ответа, ошибки после delta и совместимости `run`.

**GREEN/REFACTOR:** сделать потоковый loop единственным источником поведения и
оставить `run` тонким collector.

**Проверка:**

```sh
uv run --project backend --locked pytest backend/tests/unit/agent/test_runtime.py backend/tests/unit/agent/test_tools.py
```

## Задача 4. События и подписки `AgentService`

**Требования:** REQ-011–REQ-015, REQ-021–REQ-022, REQ-030.

**Результат:** service публикует `message_start/delta/end/error` всем активным
подписчикам диалога. Ограниченная subscriber queue отключает медленного клиента;
agent loop и сохранение истории от подписчиков не зависят. Shutdown очищает
подписки и задачи.

**Зависимости:** задача 3.

**Предполагаемые файлы:**

- `backend/src/smeshariki_ai/application/agent_service.py`;
- `backend/src/smeshariki_ai/application/events.py`;
- `backend/src/smeshariki_ai/application/__init__.py`;
- `backend/tests/unit/application/test_agent_service.py`.

**RED:** добавить тесты порядка событий, persist-before-end, ошибки после
частичного текста, broadcast, disconnect, overflow, отсутствие подписчиков и
shutdown.

**GREEN/REFACTOR:** реализовать подписку как async context manager/iterator с
идемпотентной очисткой и неблокирующей публикацией.

**Проверка:**

```sh
uv run --project backend --locked pytest backend/tests/unit/application/test_agent_service.py
```

## Задача 5. SSE HTTP-контракт

**Требования:** REQ-016–REQ-022, REQ-030.

**Результат:** `GET /api/v1/dialogs/{dialog_id}/events` возвращает корректный
SSE stream, JSON frames и heartbeat; ошибки до открытия потока используют
422/404/503. Disconnect освобождает подписку.

**Зависимости:** задача 4.

**Предполагаемые файлы:**

- `backend/src/smeshariki_ai/api/app.py`;
- `backend/tests/integration/api/test_dialogs.py`;
- `backend/tests/integration/api/test_sse.py`.

**RED:** добавить HTTP-тесты точных headers и frames, heartbeat, ошибок,
переподключения без replay и неизменного POST-контракта.

**GREEN/REFACTOR:** форматировать SSE только в HTTP-слое через стандартный
`StreamingResponse`, не добавляя стороннюю зависимость.

**Проверка:**

```sh
uv run --project backend --locked pytest backend/tests/integration/api/test_dialogs.py backend/tests/integration/api/test_sse.py
```

## Задача 6. Самодостаточная `/agent_test`

**Требования:** REQ-023–REQ-029.

**Результат:** FastAPI отдаёт один package HTML resource с минимальными
встроенными стилями и vanilla JavaScript. Страница создаёт диалог, ждёт `ready`,
отправляет сообщения, постепенно строит ответ через `textContent`, отображает
ошибки и умеет начать новый диалог.

**Зависимости:** задача 5.

**Предполагаемые файлы:**

- `backend/src/smeshariki_ai/api/app.py`;
- `backend/src/smeshariki_ai/api/agent_test.html`;
- `backend/pyproject.toml`;
- `backend/tests/integration/api/test_agent_test.py`.

**RED:** добавить HTTP-тест ответа, media type, отсутствия внешних ресурсов и
наличия публичных API URL; XSS-безопасность JavaScript проверить ревью способа
DOM-вставки.

**GREEN/REFACTOR:** подключить package resource и route без static mount,
template engine или frontend toolchain.

**Проверка:**

```sh
uv run --project backend --locked pytest backend/tests/integration/api/test_agent_test.py
```

Дополнительно выполнить ручной smoke после `make run`: открыть `/agent_test`,
дождаться ready, отправить запрос и увидеть постепенное обновление ответа.

## Задача 7. Контрактная документация

**Требования:** REQ-020, REQ-031.

**Результат:** архитектурный каталог и инструкции отражают streaming provider,
agent stream, in-memory SSE broadcast, отсутствие replay/CORS и назначение
`/agent_test`; устаревшие утверждения об отсутствии streaming/SSE удалены.

**Зависимости:** задачи 1–6.

**Предполагаемые файлы:**

- `docs/agent.md`;
- `docs/dialogs.md`;
- `docs/README.md`;
- `backend/README.md`;
- `AGENTS.md`.

**Проверка:** ревью ссылок, endpoint, событий, ограничений и соответствия
фактической реализации. Автотесты наличия документации не добавляются.

## Задача 8. Интеграционная проверка реализации

**Требования:** REQ-032 и все критерии приёмки.

**Результат:** весь продуктовый набор тестов и Ruff проходят; изменения не
нарушают bootstrap, конфигурацию, старые диалоговые контракты и Docker-границы.

**Зависимости:** задачи 1–7.

**Предполагаемые файлы:** только исправления первопричин в файлах предыдущих
задач.

**Проверка:**

```sh
make test
make lint
```

После реализации перейти к отдельному этапу verify и создать
`specs/changes/agent-sse-test-ui/verification.md` только на основании
фактических результатов команд и ревью.
