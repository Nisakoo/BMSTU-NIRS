# План: настраиваемое логирование backend

## Основание и порядок

План реализует согласованную [спецификацию](./spec.md). Работа выполняется
последовательно: сначала фиксируется фактический потоковый контракт LiteLLM,
затем вводятся безопасный формат и конфигурация, потом контекст HTTP/фоновых
задач, затем метрики LLM и остальные события. Это позволяет проверять каждый
слой отдельно и не переписывать одновременно HTTP, agent loop и провайдера.

На этапе `plan` производственный код и тесты не меняются. Во время реализации
каждая задача проходит RED → GREEN → REFACTOR, а после всех задач выполняются
`make test`, `make lint` и проверка обоих форматов при запуске приложения.

## Решения и риски

1. Корневой `Config` получает вложенный `logging` подконфиг; `load_config`
   остаётся единственным читателем environment. Настройка Python-логгера
   ограничивается namespace приложения. Текущую настройку через
   `logging.basicConfig` заменяет явная конфигурация обработчика, чтобы не
   повышать уровень сторонних библиотек и не зависеть от инициализации Uvicorn.
2. Внутренняя запись события формируется из стабильного `event` и набора
   разрешённых полей. Форматтеры `human` и `json` получают одни и те же
   структурированные значения. Произвольные `record.msg`, exception text,
   `exc_info`, HTTP payload и SDK kwargs не сериализуются. Контекстные поля
   заполняются только из проверенных ID и безопасных чисел/статусов.
3. HTTP-граница создаёт серверный UUID `request_id` и возвращает
   `X-Request-ID`. Для фоновой задачи контекст захватывается в момент её
   создания; для прямого вызова `Agent` без HTTP он остаётся пустым. Контекст
   одной задачи очищается после завершения. `dialog_id` берётся из проверенного
   маршрута/сервисного вызова, а в строку маршрута попадает шаблон FastAPI.
4. Терминальные операции используют UTC `started_at` и монотонную длительность;
   `timestamp` форматтера указывает время записи. Границы HTTP-запроса,
   фонового запуска, LLM и инструмента тестируются отдельно, включая ошибку
   и отмену. Медленный SSE-запрос измеряется до закрытия потока, а не только
   до создания `StreamingResponse`.
5. У LiteLLM в локально установленном SDK есть `stream_options` и поле
   `ModelResponseStream.usage`; текущий адаптер пропускает чанки без `choices`.
   Первая задача подтвердит на зафиксированной версии SDK, как запросить и
   прочитать usage chunk. Если конкретный upstream usage не предоставляет,
   `usage_available=false`; токены не оцениваются по тексту. Проверяется
   совместимость с текущими потоковыми test doubles и провайдерами без usage.
6. `call_id` LLM создаётся на каждый вызов stream; `tool_call_id` берётся из
   `ToolCall.id`. Оба идентификатора могут присутствовать одновременно в
   событии исполнения инструмента, но имеют разную семантику. Для пары
   `llm.request.started`/терминальное событие используется один `call_id`.
7. Собственный HTTP access event заменяет дублирующий Uvicorn access log в
   штатном запуске. Параметры запроса не выводятся. Проверяется, что вывод
   Uvicorn/LiteLLM не обходит политику безопасности при `DEBUG`.

## Задача 1. Подтвердить потоковый контракт usage LiteLLM

**Требования:** REQ-007–REQ-008. **Зависимости:** нет.

**Результат:** зафиксировано, как зафиксированная версия LiteLLM принимает
`stream_options={"include_usage": True}` и отдаёт terminal chunk с usage,
в том числе с пустым `choices`; отсутствие и некорректность usage описаны как
отдельные проверяемые случаи. Код продукта пока не меняется.

**Файлы:** `backend/uv.lock`, установленный пакет LiteLLM — чтение;
`backend/tests/unit/agent/providers/test_litellm.py` — тестовые фикстуры на
следующем шаге.

**Проверка:** просмотр SDK и существующих тестов; затем точная тестовая команда
для этой области при реализации:

```sh
uv run --project backend --locked pytest backend/tests/unit/agent/providers/test_litellm.py
```

## Задача 2. Ввести конфигурацию и два формата записи

**Требования:** REQ-001–REQ-003, REQ-010–REQ-012. **Зависимости:** задача 1.

**Результат:** `LOG_LEVEL` и `LOG_FORMAT` валидируются, `human` и `json`
сериализуют общую схему без payload, повторная инициализация не дублирует
строки и не меняет уровни зависимостей. Существующие события приложения
остаются наблюдаемыми до миграции их полей.

**Файлы:** `backend/src/smeshariki_ai/config.py`,
`backend/src/smeshariki_ai/bootstrap.py`, новый внутренний модуль форматирования
логов, `backend/tests/unit/test_backend_config.py`,
`backend/tests/unit/test_bootstrap.py`.

**Проверка:** тесты значений по умолчанию, невалидной конфигурации, JSON типов,
UTC timestamps, null ID, human вывода, повторной настройки и секретных
маркеров.

```sh
uv run --project backend --locked pytest backend/tests/unit/test_backend_config.py backend/tests/unit/test_bootstrap.py
```

## Задача 3. Связать HTTP-запрос с фоновым сообщением

**Требования:** REQ-004–REQ-005, REQ-012. **Зависимости:** задача 2.

**Результат:** HTTP API генерирует `request_id` и возвращает его для успешных
и ошибочных ответов. События содержат безопасный шаблон маршрута,
`started_at`, `duration_ms`, статус и outcome. Принятое сообщение сохраняет
контекст своего POST до завершения фоновой обработки; независимые запросы его
не разделяют.

**Файлы:** `backend/src/smeshariki_ai/api/app.py`,
`backend/src/smeshariki_ai/application/agent_service.py`, внутренний модуль
контекста логирования, `backend/tests/integration/api/test_dialogs.py`,
`backend/tests/unit/application/test_agent_service.py`.

**Проверка:** 201/202/4xx/5xx и SSE disconnect, две очередные задачи одного
диалога, два параллельных диалога и отсутствие текстов в логах.

```sh
uv run --project backend --locked pytest backend/tests/integration/api/test_dialogs.py backend/tests/integration/api/test_sse.py backend/tests/unit/application/test_agent_service.py
```

## Задача 4. Структурировать события agent loop и инструментов

**Требования:** REQ-006, REQ-010, REQ-012. **Зависимости:** задача 3.

**Результат:** агент наследует `request_id`/`dialog_id`, сохраняет номер
итерации; события инструмента имеют `tool_call_id`, имя, исход, `started_at`
и `duration_ms`. Ошибки и отмена имеют терминальную запись без содержимого
аргументов/исключений. Прямые unit-вызовы без HTTP работают без ложного ID.

**Файлы:** `backend/src/smeshariki_ai/agent/runtime.py`,
`backend/src/smeshariki_ai/agent/tools.py`,
`backend/tests/unit/agent/test_runtime.py`,
`backend/tests/unit/agent/test_tools.py`.

**Проверка:** успешный вызов, неизвестный tool, ошибка валидации, ошибка
исполнения, отмена, изоляция одновременных запусков и приватные маркеры.

```sh
uv run --project backend --locked pytest backend/tests/unit/agent/test_runtime.py backend/tests/unit/agent/test_tools.py
```

## Задача 5. Измерить LLM stream и сохранить usage

**Требования:** REQ-006–REQ-008, REQ-010, REQ-012. **Зависимости:** задачи 1,
3 и 4.

**Результат:** каждый вызов провайдера получает `call_id`, записывает старт
и ровно один терминальный исход с `started_at`, `duration_ms` и безопасным
`error_type` при ошибке. `time_to_first_token_ms` измеряется по первому
непустому текстовому delta, если он есть. Чанк usage обрабатывается даже при
пустом `choices`; токены записываются только после проверки целочисленности
и неотрицательности. Поток текста/tool calls и отмена сохраняют поведение.

**Файлы:** `backend/src/smeshariki_ai/agent/providers/litellm.py`,
`backend/tests/unit/agent/providers/test_litellm.py`,
`backend/tests/integration/api/test_litellm_provider.py`.

**Проверка:** модельные потоки с usage и без него, empty choices, ошибки до
первого чанка и во время потока, отмена, tool call, отсутствие секретов.

```sh
uv run --project backend --locked pytest backend/tests/unit/agent/providers/test_litellm.py backend/tests/integration/api/test_litellm_provider.py
```

## Задача 6. Показать потерю SSE-подписчика

**Требования:** REQ-009, REQ-010, REQ-012. **Зависимости:** задача 3.

**Результат:** переполнение очереди и принудительное закрытие видны как
`WARNING` с `dialog_id` и безопасной причиной. Агент и запись истории не
зависят от медленной подписки.

**Файлы:** `backend/src/smeshariki_ai/application/event_broker.py`,
`backend/tests/unit/application/test_event_broker.py`,
`backend/tests/integration/api/test_sse.py`.

**Проверка:** ограниченная очередь, несколько подписчиков, отсутствие
payload в событии и успешное завершение фоновой задачи.

```sh
uv run --project backend --locked pytest backend/tests/unit/application/test_event_broker.py backend/tests/integration/api/test_sse.py
```

## Задача 7. Подключить штатный запуск Compose

**Требования:** REQ-001, REQ-011–REQ-013. **Зависимости:** задачи 2–6.

**Результат:** `LOG_LEVEL`/`LOG_FORMAT` проходят через Compose; штатный
запуск не создаёт небезопасный дублирующий access log.

**Файлы:** `docker/compose.yaml`, `docker/.env.example`, `docker/Dockerfile`.
При необходимости настройка запуска переносится в файл внутри `docker/` по
архитектурному правилу репозитория.

**Проверка:** ревью конфигурации, `docker compose config` с тестовыми
несекретными значениями; без тестов наличия файлов.

```sh
LLM_MODEL=test/model docker compose -f docker/compose.yaml config --quiet
```

## Задача 8. Описать контракт логирования

**Требования:** REQ-003–REQ-013. **Зависимости:** задачи 2–7.

**Результат:** документация описывает общие поля, оба формата, поиск по ID,
уровни и ограничения метрик usage; архитектурный каталог указывает владельца
конфигурации и журнала.

**Файлы:** `docs/configuration.md`, `docs/README.md`, новая тематическая
страница логирования.

**Проверка:** ревью документации относительно спецификации и фактического
вывода; искусственные тесты на наличие файлов не создаются.

## Задача 9. Проверить сквозной контракт и регрессии

**Требования:** REQ-001–REQ-013. **Зависимости:** задачи 2–8.

**Результат:** интеграционные тесты подтверждают связь одной операции через
HTTP, agent, LLM и tool, корректные времена/исходы в двух форматах,
разделение параллельных запросов и безопасность вывода на `DEBUG`.
Обновляются только те существующие тесты, которые проверяют старую строковую
схему логов; проверки поведения агента и SSE остаются содержательными.

**Файлы:** `backend/tests/integration/api/test_dialogs.py`,
`backend/tests/integration/api/test_litellm_provider.py`,
`backend/tests/integration/api/test_sse.py`, при необходимости отдельный
интеграционный файл для лог-контракта.

**Проверка:** адресные интеграционные тесты, полный продуктовый набор,
Ruff и ручная проверка читаемости двух форматов.

```sh
uv run --project backend --locked pytest backend/tests/integration/api
make test
make lint
```

## Критерий завершения

После реализации выполняется отдельный этап `verify` по SDD: фиксируются
команды и результаты в `verification.md`; статус `done` устанавливается только
после успешных проверок. Если какое-либо поле usage недоступно у реального
провайдера, отчёт прямо показывает `usage_available=false` и проверенный
сценарий, а не выдаёт неподтверждённые числа.
