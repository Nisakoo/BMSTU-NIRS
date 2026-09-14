# План: минимальный runtime агента

## Основание

План реализует согласованную спецификацию
`specs/changes/agent-runtime/spec.md`. Изменение создаёт только внутренний
runtime агента: доменные модели, абстракцию LLM, fake-провайдер, инструменты,
реестр и собственный ограниченный tool-calling loop. HTTP, история диалогов,
RAG и реальный LLM-провайдер остаются за границами этой работы.

## Решения и зависимости

Backend оформляется как самостоятельный uv-проект в `backend/` с импортируемым
пакетом `smeshariki_ai` в существующем `src`-layout. Команды из корня используют
явный `--project backend`, поэтому frontend остаётся независимым.

На 13 сентября 2026 года используются следующие совместимые диапазоны стабильных
релизов; точное разрешение фиксируется в `backend/uv.lock`:

- Python `>=3.12,<3.13`;
- Pydantic `>=2.13.5,<3`;
- Pytest `>=9.1.1,<10`;
- pytest-asyncio `>=1.4.0,<2`;
- Hatchling `>=1.32.0,<2` как build backend.

Pydantic является единственной runtime-зависимостью. Pytest и pytest-asyncio
попадают в dev dependency group; Hatchling используется только системой сборки.
LangChain, LangGraph и SDK поставщиков LLM не добавляются.

Ключевое модельное решение: `LLMResponse.content` различает `None` и пустую
строку. `content=""` является корректным финальным ответом, а `None` без tool
call — некорректным ответом провайдера. Один ответ может содержать максимум один
tool call.

## Порядок реализации

1. Настроить воспроизводимый Python-проект и настоящий вход `make test`.
2. Ввести доменные модели и абстракцию LLM с пустым fake-ответом.
3. Реализовать контракт `Tool` и безопасный `ToolRegistry`.
4. Реализовать успешные пути `Agent.run` через TDD.
5. Добавить ошибки, лимит итераций и безопасную наблюдаемость loop.
6. Опубликовать внутренний API пакета и актуализировать архитектурные правила.
7. Выполнить итоговую проверку всей спецификации.

Каждый следующий шаг зависит от предыдущего. Самыми рискованными решениями —
различие `None`/`""`, форма tool messages и безопасное преобразование ошибок —
занимаются задачи 2–5 до документирования публичных импортов.

## Задача 1. Настроить uv-проект backend и тестовую команду

**Связанные требования:** REQ-007, REQ-013, REQ-014.

**Критерии приёмки:** проект описывает Python 3.12, имя дистрибутива
`smeshariki-ai`, согласованные зависимости и `src`-layout; lock-файл актуален;
`make test` вызывает Pytest только через uv.

**Зависимости:** нет.

**Файлы:**

- `backend/pyproject.toml`;
- `backend/uv.lock`;
- `.gitignore`;
- `Makefile`.

**Действия:**

1. Добавить метаданные проекта, `requires-python`, Hatchling и явный путь
   `src/smeshariki_ai`.
2. Добавить Pydantic в runtime dependencies, Pytest и pytest-asyncio в dev
   dependency group, настроить asyncio-режим тестов.
3. Создать lock-файл только через `uv lock --project backend`.
4. Настроить `.gitignore` для `.venv`, Python bytecode и кэшей тестов.
5. Заменить заглушку `make test` на
   `uv run --project backend --locked pytest` без использования pip.
6. Не менять цель `make run`: исполняемое приложение не входит в эту
   спецификацию.

**Проверка:**

```sh
uv lock --project backend --check
uv run --project backend --locked python -c "import pydantic; print(pydantic.__version__)"
```

На этом инфраструктурном шаге отдельный тест структуры не создаётся; `make test`
начнёт успешно выполняться после появления первого продуктового теста в задаче
2.

## Задача 2. Ввести доменные модели и LLMProvider

**Связанные требования:** REQ-002, REQ-003, REQ-006, REQ-007, REQ-008.

**Критерии приёмки:** внутренние Pydantic-модели выражают сообщения, конфигурацию
агента, финальный ответ и одиночный tool call; пустая строка не смешивается с
отсутствующим ответом; `FakeLLMProvider` всегда асинхронно возвращает пустой
финальный ответ без сети.

**Зависимости:** задача 1.

**Файлы:**

- `backend/src/smeshariki_ai/agent/models.py`;
- `backend/src/smeshariki_ai/agent/llm.py`;
- `backend/src/smeshariki_ai/agent/errors.py`;
- `backend/tests/unit/agent/test_llm.py`.

**Действия (RED → GREEN → REFACTOR):**

1. Написать падающие тесты доменных контрактов и пустого fake-ответа.
2. Определить `Message`, `UserRequest`, `AgentConfig`, `ToolDefinition`,
   `ToolCall`, `ToolResult`, `LLMResponse` и `AgentResponse` без типов SDK
   поставщика.
3. Установить `max_iterations=4` по умолчанию и запретить неположительный лимит.
4. Определить асинхронный абстрактный `LLMProvider.generate(messages, tools)`.
5. Реализовать `FakeLLMProvider`, возвращающий `LLMResponse(content="")` и
   пустой список tool calls независимо от входа.
6. Ввести доменные исключения для некорректного ответа LLM и исчерпания лимита,
   не связывая их с HTTP.

**Тест:**

```sh
uv run --project backend --locked pytest backend/tests/unit/agent/test_llm.py
```

## Задача 3. Реализовать Tool и ToolRegistry

**Связанные требования:** REQ-004, REQ-009, REQ-010, REQ-011, REQ-012.

**Критерии приёмки:** реестр принимает экземпляры наследников `Tool`, строит
стабильные определения для LLM, валидирует аргументы и возвращает безопасный
`ToolResult` для успеха, неизвестного имени, ошибки валидации и исключения.

**Зависимости:** задача 2.

**Файлы:**

- `backend/src/smeshariki_ai/agent/tools.py`;
- `backend/src/smeshariki_ai/agent/errors.py`;
- `backend/tests/unit/agent/test_tools.py`.

**Действия (RED → GREEN → REFACTOR):**

1. Написать падающие тесты пустого реестра, регистрации, JSON Schema,
   дубликатов, выполнения и всех безопасных ошибок.
2. Определить абстрактный `Tool` с `name`, `description`, Pydantic-моделью
   аргументов и `async execute(validated_arguments)`.
3. При создании `ToolRegistry` сохранить переданную последовательность в
   неизменяемом отображении и немедленно отклонить повторяющиеся имена.
4. Реализовать получение `ToolDefinition` в детерминированном порядке.
5. Реализовать `ToolRegistry.execute(tool_call)`: поиск только по реестру,
   Pydantic-валидация до исполнения и преобразование ожидаемых ошибок в
   JSON-совместимый `ToolResult` с кодами `tool_not_found`,
   `invalid_arguments` и `tool_execution_failed`.
6. Не включать traceback, исходные аргументы или текст исключения в результат,
   возвращаемый LLM.

**Тест:**

```sh
uv run --project backend --locked pytest backend/tests/unit/agent/test_tools.py
```

## Задача 4. Реализовать успешные пути Agent.run

**Связанные требования:** REQ-001, REQ-002, REQ-003, REQ-004, REQ-006.

**Критерии приёмки:** агент не изменяет входную историю, завершает прямой ответ,
выполняет один tool call через реестр, добавляет вызов и результат в рабочий
контекст и возвращает следующий финальный ответ.

**Зависимости:** задачи 2 и 3.

**Файлы:**

- `backend/src/smeshariki_ai/agent/runtime.py`;
- `backend/tests/unit/agent/test_runtime.py`.

**Действия (RED → GREEN → REFACTOR):**

1. В тестах создать локальные `ScriptedLLMProvider` и `RecordingTool`, чтобы
   управлять последовательностью ответов без расширения production fake.
2. Написать падающий тест прямого пустого ответа и неизменности исходной
   истории.
3. Реализовать `Agent.__init__(llm_provider, tool_registry, config)` без чтения
   environment и `async Agent.run(history, request)` с отдельным рабочим
   контекстом.
4. Добавлять системную инструкцию из `AgentConfig`, историю и новый запрос в
   однозначном порядке и передавать определения реестра на каждом шаге.
5. Написать падающий тест последовательности
   `tool call → ToolResult → final response`.
6. Реализовать повторный вызов LLM с доменными сообщениями о вызове и результате
   инструмента; инструмент выполнять только через `ToolRegistry`.
7. Явно считать `content=""` финальным ответом, проверяя `is not None`, а не
   truthiness строки.

**Тест:**

```sh
uv run --project backend --locked pytest backend/tests/unit/agent/test_runtime.py -k "direct or tool"
```

## Задача 5. Добавить защитные ветви и серверное логирование

**Связанные требования:** REQ-005, REQ-006, REQ-011, REQ-012, REQ-016.

**Критерии приёмки:** некорректный LLM-ответ и пятая итерация невозможны;
ошибочные tool calls возвращаются в контекст как безопасные результаты; журнал
показывает переходы loop без пользовательского содержимого и tool payload.

**Зависимости:** задача 4.

**Файлы:**

- `backend/src/smeshariki_ai/agent/runtime.py`;
- `backend/src/smeshariki_ai/agent/errors.py`;
- `backend/tests/unit/agent/test_runtime.py`;
- `backend/tests/unit/agent/test_tools.py`.

**Действия (RED → GREEN → REFACTOR):**

1. Добавить падающие тесты ответа одновременно с текстом и tool call,
   нескольких tool calls, отсутствия обоих вариантов и лимита четырёх шагов.
2. Проверять форму каждого `LLMResponse` до исполнения tool call и выбрасывать
   доменный `InvalidLLMResponseError` для неоднозначного ответа.
3. После четвёртого ответа без финального текста завершать
   `AgentIterationLimitError`, не выполняя пятый вызов LLM.
4. Проверить продолжение loop после `tool_not_found`, `invalid_arguments` и
   `tool_execution_failed`.
5. Добавить стабильные log events `agent.run.started`,
   `agent.iteration.started`, `agent.llm.completed`, `agent.tool.completed`,
   `agent.run.completed` и `agent.run.failed` с номером шага, именем инструмента
   и статусом там, где применимо.
6. Тестами `caplog` доказать отсутствие полного request/history, аргументов,
   результата инструмента и текста исключения в журнале.

**Тест:**

```sh
uv run --project backend --locked pytest backend/tests/unit/agent/test_runtime.py backend/tests/unit/agent/test_tools.py
```

## Задача 6. Опубликовать контракт и актуализировать AGENTS.md

**Связанные требования:** REQ-001, REQ-007, REQ-009, REQ-013, REQ-015.

**Критерии приёмки:** согласованные типы импортируются из пакета `agent`, а
`AGENTS.md` описывает только действительно реализованный runtime и не объявляет
готовыми HTTP, историю, RAG или реальный LLM.

**Зависимости:** задачи 2–5.

**Файлы:**

- `backend/src/smeshariki_ai/agent/__init__.py`;
- `AGENTS.md`.

**Действия:**

1. Экспортировать минимальный поддерживаемый внутренний контракт: `Agent`,
   `AgentConfig`, сообщения и ответы, `LLMProvider`, `FakeLLMProvider`, `Tool` и
   `ToolRegistry`.
2. Дополнить согласованную архитектуру в `AGENTS.md` фактическими ролями классов,
   лимитом loop, правилами tool validation и безопасного логирования.
3. Явно оставить `AgentService`, HTTP, историю, `search_knowledge` и реальный
   provider будущими изменениями.

**Проверка ревью:**

```sh
sed -n '1,260p' AGENTS.md
uv run --project backend --locked python -c "from smeshariki_ai.agent import Agent, FakeLLMProvider, ToolRegistry"
```

Отдельный автоматический тест текста `AGENTS.md` не добавляется.

## Итоговая проверка реализации

**Связанные требования:** REQ-001–REQ-016 и все критерии приёмки.

1. Запустить полный продуктовый набор тестов из корня:

   ```sh
   make test
   ```

2. Проверить актуальность lock-файла:

   ```sh
   uv lock --project backend --check
   ```

3. Проверить публичные импорты runtime:

   ```sh
   uv run --project backend --locked python -c "from smeshariki_ai.agent import Agent, FakeLLMProvider, Tool, ToolRegistry"
   ```

4. Просмотреть зависимости и убедиться, что отсутствуют LangChain, LangGraph,
   FastAPI, Qdrant и SDK поставщиков LLM:

   ```sh
   uv tree --project backend
   ```

5. Сопоставить каждый REQ и критерий спецификации с тестом либо результатом
   ревью. Не создавать тесты, проверяющие только дерево файлов или документацию.
6. Убедиться, что `make run` и файлы `docker/` не изменены этим изменением.

После реализации перейти к отдельному этапу `verify`, записать результаты в
`specs/changes/agent-runtime/verification.md` и только после успешной проверки
установить статус `done`.
