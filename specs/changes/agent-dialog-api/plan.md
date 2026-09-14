# План: диалоги агента и фоновый HTTP-запуск

## Основание

План реализует одобренную спецификацию
`specs/changes/agent-dialog-api/spec.md` поверх готового `agent-runtime`.
Изменение добавляет in-memory историю, сервис постановки запросов в фон и
минимальное FastAPI-приложение. Frontend, SSE, получение истории и результата,
реальный LLM, RAG, CORS, cookie-сессии и внешняя очередь остаются вне scope.

## Решения и зависимости

На 13 сентября 2026 года план фиксирует следующие диапазоны актуальных
стабильных релизов; точные версии и транзитивные зависимости будут разрешены
только через `uv` и записаны в `backend/uv.lock`:

- FastAPI `>=0.141.1,<1` — runtime HTTP API;
- Uvicorn `>=0.52.4,<1` — ASGI-сервер для контейнерного запуска;
- HTTPX `>=0.28.1,<1` — dev-зависимость для ASGI HTTP-тестов.

Используются минимальные пакеты FastAPI и Uvicorn без `standard` extras, чтобы
не добавлять CLI, шаблонизаторы, формы, WebSocket-ускорители и другие
невостребованные зависимости. Конфигурация приложения валидируется Pydantic и
читается небольшим адаптером из environment без добавления
`pydantic-settings`.

### История

`HistoryStore` предоставляет асинхронные операции `create()`, `get(dialog_id)`
и атомарный `append(dialog_id, messages)`. Пакетное добавление необходимо,
чтобы пользовательское и финальное сообщения не могли сохраниться частично.
`InMemoryHistoryStore` защищает отображение диалогов одним `asyncio.Lock`,
возвращает неизменяемый снимок истории и создаёт UUID через `uuid4()`.

### Очередь и lifecycle

`AgentService.submit` сначала подтверждает существование диалога, затем под
коротким внутренним lock создаёт фоновую задачу и возвращает управление. Для
каждого `dialog_id` хранится последняя задача: новая задача ожидает предыдущую,
после чего заново читает завершённую историю и запускает `Agent`. Поэтому
запросы одного диалога выполняются строго последовательно, а задачи разных
диалогов не ожидают друг друга.

Сервис хранит сильные ссылки на все задачи, как рекомендует документация
`asyncio` для fire-and-forget работы. Фоновая ошибка перехватывается и
журналируется без изменения истории. `CancelledError` журналируется отдельно и
пробрасывается после cleanup. `shutdown()` атомарно запрещает новые submit,
отменяет незавершённые задачи и ожидает их через `gather(return_exceptions=True)`.
Попытка submit после закрытия сервиса преобразуется в доменную ошибку
недоступности и HTTP 503.

### HTTP и сборка приложения

HTTP-слой создаётся фабрикой `create_app(agent_service)` и получает готовый
сервис из пакета `smeshariki_ai.application`, не собирая зависимости внутри
маршрутов. Контракт и реализация истории остаются в пакете
`smeshariki_ai.dialogs`. FastAPI lifespan вызывает
`AgentService.shutdown()` при остановке. Bootstrap отдельно загружает config и
однократно создаёт `FakeLLMProvider`, пустой `ToolRegistry`, `Agent`,
`InMemoryHistoryStore`, `AgentService` и приложение. `smeshariki_ai.main:app`
становится ASGI entrypoint.

Контейнер использует Python 3.12 slim и официальный образ uv, закреплённый на
версии `0.12.13`; установка выполняется из lock-файла без dev-зависимостей.
Compose публикует только backend и не содержит frontend.

## Порядок реализации

1. Добавить и зафиксировать HTTP-зависимости.
2. Реализовать контракт и in-memory реализацию истории.
3. Реализовать постановку в очередь, порядок и независимость диалогов.
4. Добавить ошибки, lifecycle фоновых задач и безопасные логи сервиса.
5. Реализовать HTTP-контракты и их интеграционные тесты.
6. Собрать запускаемое приложение и конфигурацию.
7. Создать воспроизводимый образ backend.
8. Подключить Compose и документацию запуска.
9. Актуализировать `AGENTS.md`.
10. Выполнить итоговый Verify.

Рискованные части — атомарность истории, возврат HTTP до завершения агента и
корректная отмена задач — проверяются в задачах 2–5 до контейнеризации.

## Задача 1. Добавить HTTP- и тестовые зависимости

**Связанные требования:** REQ-013–REQ-021.

**Критерии приёмки:** FastAPI и Uvicorn являются runtime-зависимостями, HTTPX —
dev-зависимостью; lock-файл актуален; пакеты импортируются на Python 3.12.

**Зависимости:** реализованный `agent-runtime`.

**Файлы:**

- `backend/pyproject.toml`;
- `backend/uv.lock`.

**Действия:**

1. Добавить диапазоны зависимостей только через uv-проект backend.
2. Не добавлять SSE-, CORS-, broker-, database- или LLM-пакеты.
3. Проверить lock и фактически разрешённые версии.

**Проверка:**

```sh
uv lock --project backend --check
uv run --project backend --locked python -c "import fastapi, httpx, uvicorn"
```

Отдельный структурный тест зависимостей не создаётся.

## Задача 2. Реализовать HistoryStore и InMemoryHistoryStore

**Связанные требования:** REQ-001, REQ-002, REQ-006–REQ-008.

**Критерии приёмки:** создаётся уникальный UUIDv4 и пустая история; диалоги
изолированы; чтение возвращает снимок; batch append сохраняет порядок атомарно;
неизвестный UUID приводит к доменной ошибке.

**Зависимости:** задача 1.

**Файлы:**

- `backend/src/smeshariki_ai/dialogs/errors.py`;
- `backend/src/smeshariki_ai/dialogs/history.py`;
- `backend/src/smeshariki_ai/dialogs/__init__.py`;
- `backend/tests/unit/dialogs/test_history.py`.

**Действия (RED → GREEN → REFACTOR):**

1. Сначала написать тесты создания, UUID version 4, пустого чтения, изоляции,
   порядка batch append и неизвестного диалога.
2. Определить асинхронный ABC `HistoryStore` с `create`, `get` и `append`.
3. Реализовать защищённое lock in-memory отображение `UUID → list[Message]`.
4. Никогда не возвращать вызывающему изменяемый внутренний список.

**Тест:**

```sh
uv run --project backend --locked pytest backend/tests/unit/dialogs/test_history.py
```

## Задача 3. Реализовать успешные пути AgentService

**Связанные требования:** REQ-003–REQ-007, REQ-009.

**Критерии приёмки:** `start_dialog` делегирует создание хранилищу; `submit`
возвращается после создания задачи; успешный запуск сохраняет только пару
user/assistant; второй запрос одного диалога видит результат первого; разные
диалоги могут исполняться одновременно.

**Зависимости:** задача 2.

**Файлы:**

- `backend/src/smeshariki_ai/application/agent_service.py`;
- `backend/src/smeshariki_ai/application/__init__.py`;
- `backend/tests/unit/application/test_agent_service.py`.

**Действия (RED → GREEN → REFACTOR):**

1. Создать тестовый управляемый агент, записывающий полученную историю и
   блокируемый через `asyncio.Event`.
2. Тестом доказать, что `submit` завершается при заблокированном агенте.
3. Реализовать цепочку задач по `dialog_id` и общий набор сильных ссылок на
   незавершённые задачи.
4. Загружать историю только внутри фоновой обработки после предыдущей задачи.
5. После успеха одним `append` сохранить `MessageRole.USER`, затем
   `MessageRole.ASSISTANT`; внутренний контекст Agent не сохранять.
6. Проверить последовательность одного диалога и независимость двух диалогов.

**Тест:**

```sh
uv run --project backend --locked pytest backend/tests/unit/application/test_agent_service.py -k "submit or order or independent"
```

## Задача 4. Добавить ошибки, shutdown и безопасное логирование AgentService

**Связанные требования:** REQ-008, REQ-010, REQ-012, REQ-017.

**Критерии приёмки:** ошибка агента не меняет историю и не выходит из фоновой
задачи; shutdown закрывает submit, отменяет и дожидается задач; отмена не
порождает unhandled exception; все события содержат `dialog_id`, но не payload.

**Зависимости:** задача 3.

**Файлы:**

- `backend/src/smeshariki_ai/application/errors.py`;
- `backend/src/smeshariki_ai/application/agent_service.py`;
- `backend/tests/unit/application/test_agent_service.py`.

**Действия (RED → GREEN → REFACTOR):**

1. Добавить тесты неизвестного диалога и отказа submit после shutdown.
2. Добавить тест фоновой ошибки с неизменной историей.
3. Реализовать `shutdown`: запрет новых submit, cancel, await и очистка ссылок.
4. В done callback забирать результат задачи, чтобы не оставлять
   `Task exception was never retrieved`.
5. Добавить события `dialog.created`, `dialog.request.accepted`,
   `dialog.run.started`, `dialog.run.completed`, `dialog.history.persisted`,
   `dialog.run.cancelled` и `dialog.run.failed`.
6. Через `caplog` проверить отсутствие request/history/response и текста
   исключения в журнале.

**Тест:**

```sh
uv run --project backend --locked pytest backend/tests/unit/application/test_agent_service.py
```

## Задача 5. Реализовать FastAPI-контракты диалогов

**Связанные требования:** REQ-013–REQ-019, REQ-021.

**Критерии приёмки:** создание возвращает 201, UUID JSON и Location; сообщение
возвращает пустой 202 до разблокировки агента; 404, 422 и 503 различаются;
cookie игнорируются; нет streaming media type или фонового результата в HTTP.

**Зависимости:** задача 4.

**Файлы:**

- `backend/src/smeshariki_ai/api/schemas.py`;
- `backend/src/smeshariki_ai/api/app.py`;
- `backend/src/smeshariki_ai/api/__init__.py`;
- `backend/tests/integration/api/test_dialogs.py`.

**Действия (RED → GREEN → REFACTOR):**

1. Написать HTTP-тесты через HTTPX ASGI transport и управляемый lifecycle.
2. Определить `StartDialogResponse` и входную Pydantic-схему с trim и
   `min_length=1`.
3. Реализовать фабрику `create_app(agent_service)` и два POST-маршрута.
4. Возвращать `Response(status_code=202)` без JSON body и content type.
5. Преобразовать `DialogNotFoundError` в 404 и закрытый сервис в безопасный 503;
   UUID/path и body validation оставить FastAPI для 422.
6. Подключить shutdown сервиса через FastAPI lifespan.
7. Проверить отсутствие `Set-Cookie`, CORS-заголовков и streaming response.

**Тест:**

```sh
uv run --project backend --locked pytest backend/tests/integration/api/test_dialogs.py
```

## Задача 6. Добавить конфигурацию, bootstrap и ASGI entrypoint

**Связанные требования:** REQ-011, REQ-015, REQ-020.

**Критерии приёмки:** bootstrap единожды собирает граф зависимостей с
`FakeLLMProvider` и пустым registry; сервис и runtime не читают environment;
импорт `smeshariki_ai.main:app` создаёт FastAPI-приложение без сети.

**Зависимости:** задача 5.

**Файлы:**

- `backend/src/smeshariki_ai/config.py`;
- `backend/src/smeshariki_ai/bootstrap.py`;
- `backend/src/smeshariki_ai/main.py`;
- `backend/tests/unit/test_bootstrap.py`.

**Действия (RED → GREEN → REFACTOR):**

1. Тестом проверить сборку приложения и внедрение config без запуска сервера.
2. Добавить Pydantic `ApplicationConfig` и `load_config(environ)` с настройками
   `AGENT_SYSTEM_PROMPT` и `AGENT_MAX_ITERATIONS`.
3. Собрать `AgentConfig`, fake provider, пустой `ToolRegistry`, Agent, store и
   service только в bootstrap.
4. Экспортировать объект `app` из `smeshariki_ai.main` для Uvicorn.

**Тест:**

```sh
uv run --project backend --locked pytest backend/tests/unit/test_bootstrap.py
uv run --project backend --locked python -c "from smeshariki_ai.main import app; print(app.title)"
```

## Задача 7. Создать воспроизводимый контейнер backend

**Связанные требования:** REQ-020.

**Критерии приёмки:** образ использует Python 3.12, закреплённый официальный uv,
устанавливает только locked production dependencies и запускает Uvicorn;
локальная `.venv` и Git-метаданные не входят в build context.

**Зависимости:** задача 6.

**Файлы:**

- `docker/Dockerfile`;
- `.dockerignore`.

**Действия:**

1. Использовать `python:3.12-slim` и скопировать uv из
   `ghcr.io/astral-sh/uv:0.12.13`.
2. Разделить установку зависимостей и копирование `backend/src` для кэширования.
3. Выполнять `uv sync --locked --no-dev` и запускать
   `smeshariki_ai.main:app` на `0.0.0.0:8000`.
4. Исключить `.git`, `.venv`, кэши Python и несвязанные frontend-артефакты из
   build context без включения frontend в image.

**Проверка:**

```sh
docker build -f docker/Dockerfile -t smeshariki-ai-backend .
```

Автоматический тест структуры Dockerfile не создаётся.

## Задача 8. Подключить Compose и команды запуска

**Связанные требования:** REQ-020.

**Критерии приёмки:** Compose содержит только backend, публикует настраиваемый
порт и передаёт несекретный config; `.env.example` документирует параметры;
локальный `.env` игнорируется; существующий `make run` становится рабочим.

**Зависимости:** задача 7.

**Файлы:**

- `docker/compose.yaml`;
- `docker/.env.example`;
- `docker/README.md`;
- `.gitignore`;
- `Makefile` — ревью существующей цели, изменение только при необходимости.

**Действия:**

1. Добавить единственный сервис `backend` с build context из корня.
2. Передать `AGENT_SYSTEM_PROMPT`, `AGENT_MAX_ITERATIONS` и опубликовать
   `${BACKEND_PORT:-8000}:8000`.
3. Обновить шаблон и инструкцию запуска без секретных значений.
4. Добавить `docker/.env` в `.gitignore`.
5. Проверить, что `make run` использует только `docker/compose.yaml` и при
   наличии — `docker/.env`.

**Проверка:**

```sh
docker compose -f docker/compose.yaml config
make run
```

Smoke запуска выполняется с созданием диалога через HTTP; после проверки
контейнер останавливается штатно. Отдельный тест наличия Compose-файла не
создаётся.

## Задача 9. Актуализировать AGENTS.md

**Связанные требования:** REQ-022.

**Критерии приёмки:** документ описывает только реализованные `AgentService`,
`HistoryStore`, UUIDv4, URL-контракт, фоновую очередь, немедленный пустой 202,
in-memory ограничения и отсутствие cookie/CORS/SSE.

**Зависимости:** задачи 2–8.

**Файлы:**

- `AGENTS.md`.

**Действия:**

1. Добавить фактические роли service/store и lifecycle задач.
2. Зафиксировать обязательный `dialog_id` в URL и потерю данных при рестарте.
3. Не объявлять frontend, SSE, RAG, реальный LLM и постоянное хранилище
   реализованными.

**Проверка ревью:**

```sh
sed -n '1,280p' AGENTS.md
```

Автоматический тест документации не добавляется.

## Итоговая проверка реализации

**Связанные требования:** REQ-001–REQ-022 и все критерии приёмки.

1. Запустить линтинг и полный набор продуктовых тестов из корня:

   ```sh
   make lint
   make test
   ```

2. Проверить lock и runtime-импорт:

   ```sh
   uv lock --project backend --check
   uv run --project backend --locked python -c "from smeshariki_ai.main import app"
   ```

3. Просмотреть `uv tree --project backend` и убедиться, что отсутствуют SDK LLM,
   LangChain, LangGraph, Qdrant, broker и database drivers.
4. Выполнить HTTP smoke через Compose: создать диалог, отправить сообщение,
   подтвердить `201`/`Location` и пустой `202`, затем штатно остановить backend.
5. Убедиться, что Compose не содержит frontend, CORS и SSE отсутствуют, а
   `docker/.env` игнорируется Git.
6. Сопоставить все REQ и критерии с тестами или ревью и записать результат в
   `specs/changes/agent-dialog-api/verification.md`.
7. Только после успешного Verify установить статус `done` через SDD CLI.
