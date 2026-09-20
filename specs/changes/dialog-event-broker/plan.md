# План: брокер событий диалога

## Контекст

Сейчас `AgentService` одновременно координирует очередь agent tasks и реализует
process-local pub/sub: создаёт очереди подписчиков, хранит их по `dialog_id`,
рассылает события и удаляет медленных клиентов. Изменение выделяет вторую
ответственность в обязательную зависимость `DialogEventBroker` и сохраняет
`AgentService` фасадом для проверки диалога и HTTP-слоя.

Рискованная часть изменения — корректно отделить публичный контракт подписки от
in-memory очереди, не нарушив порядок SSE-событий, disconnect и shutdown.
Поэтому сначала через отдельные unit-тесты фиксируется поведение брокера, затем
сервис переводится на делегирование, и только после этого обновляются
composition root и все вызывающие тесты.

План не предусматривает обратную совместимость конструктора `AgentService`:
готовый брокер становится обязательным аргументом, а default-реализация
создаётся только в `bootstrap.py`.

## Задача 1. Абстрактный контракт и in-memory брокер

**Требования:** REQ-001–REQ-010, REQ-017, REQ-018.

**Результат:** application-слой предоставляет абстрактный
`DialogEventBroker` с операциями `subscribe`, `unsubscribe`, `publish` и
`shutdown`, а `InMemoryDialogEventBroker` реализует bounded broadcast без
replay и backpressure.

`DialogSubscription` становится только потребительским контрактом с
`dialog_id`, состоянием закрытия и `receive()`. Конкретная
`_InMemoryDialogSubscription` вместе с синхронными внутренними операциями
`offer/close` скрывается в модуле брокера. После shutdown новая подписка
отклоняется; повторные unsubscribe/shutdown безопасны, а публикация в закрытый
брокер ничего не сохраняет.

**Зависимости:** нет.

**Предполагаемые файлы:**

- `backend/src/smeshariki_ai/application/events.py`;
- `backend/src/smeshariki_ai/application/event_broker.py`;
- `backend/src/smeshariki_ai/application/__init__.py`;
- `backend/tests/unit/application/test_event_broker.py`.

**RED:** добавить асинхронные тесты валидации размера очереди, ordered
broadcast нескольким подписчикам, изоляции диалогов, отсутствия replay,
публикации без подписчиков, overflow одного клиента, идемпотентного unsubscribe
и shutdown, разблокировки ожидающего `receive` и запрета подписки после
shutdown.

**GREEN/REFACTOR:** реализовать ABC и in-memory адаптер с собственным
`asyncio.Lock`; доставлять события через `put_nowait`, удалять только
переполненную подписку и не раскрывать очередь за пределы реализации.

**Проверка:**

```sh
uv run --project backend --locked pytest backend/tests/unit/application/test_event_broker.py
```

## Задача 2. Делегирование из `AgentService`

**Требования:** REQ-011–REQ-014, REQ-018, REQ-020.

**Результат:** `AgentService` обязательно получает `DialogEventBroker` через
конструктор и больше не содержит subscriber queue size, коллекции подписчиков,
`offer()` или алгоритм очистки. Проверка существования диалога остаётся перед
делегированием subscribe; все lifecycle-события передаются через `publish`.

Shutdown сначала закрывает вход сервиса, отменяет и дожидается фоновых agent
tasks, чтобы они могли завершить собственную публикацию, а затем вызывает
`broker.shutdown()`. Логи открытия и закрытия подписки сохраняют только
стабильное событие и `dialog_id`.

**Зависимости:** задача 1.

**Предполагаемые файлы:**

- `backend/src/smeshariki_ai/application/agent_service.py`;
- `backend/tests/unit/application/test_agent_service.py`.

**RED:** добавить тестовый recording broker для проверки точных вызовов
subscribe/unsubscribe/publish/shutdown, отсутствия subscribe для неизвестного
диалога и порядка shutdown. Существующие поведенческие тесты сервиса явно
получают `InMemoryDialogEventBroker`.

**GREEN/REFACTOR:** удалить состояние подписок и `_publish` из сервиса,
делегировать операции внедрённому контракту и сохранить прежние
`DialogEvent`/логи/ошибки.

**Проверка:**

```sh
uv run --project backend --locked pytest backend/tests/unit/application/test_agent_service.py
```

## Задача 3. Composition root и непотоковые интеграционные вызовы

**Требования:** REQ-015–REQ-017, REQ-020.

**Результат:** `bootstrap.py` создаёт ровно один
`InMemoryDialogEventBroker(queue_size=64)` на экземпляр приложения и передаёт
его в `AgentService`. Все прямые создания сервиса в тестах явно задают брокер;
сам `AgentService` не имеет fallback и не читает environment.

**Зависимости:** задача 2.

**Предполагаемые файлы:**

- `backend/src/smeshariki_ai/bootstrap.py`;
- `backend/tests/unit/test_bootstrap.py`;
- `backend/tests/integration/api/test_dialogs.py`;
- `backend/tests/integration/api/test_agent_test.py`;
- `backend/tests/integration/api/test_litellm_provider.py`.

**RED:** усилить bootstrap-тест проверкой создания и передачи конкретного
in-memory брокера. Обновить тестовые composition roots обязательной
зависимостью без изменения проверяемого HTTP-поведения.

**GREEN/REFACTOR:** собрать брокер в production composition root и устранить
все вызовы устаревшей сигнатуры конструктора.

**Проверка:**

```sh
uv run --project backend --locked pytest backend/tests/unit/test_bootstrap.py backend/tests/integration/api/test_dialogs.py backend/tests/integration/api/test_agent_test.py backend/tests/integration/api/test_litellm_provider.py
```

## Задача 4. Регрессионная проверка SSE

**Требования:** REQ-004–REQ-009, REQ-012–REQ-016, REQ-020.

**Результат:** SSE-тесты используют явно созданный брокер и подтверждают, что
выделение компонента не изменило `ready`, ordered `message_*`, heartbeat,
404/422/503, отсутствие replay и завершение потока при shutdown.

**Зависимости:** задачи 1–3.

**Предполагаемые файлы:**

- `backend/tests/integration/api/test_sse.py`;
- при обнаруженной регрессии — только первопричина в файлах задач 1–3.

**RED:** адаптировать test setup к обязательному брокеру и убедиться, что тесты
падают при потере делегирования либо неправильном закрытии подписки.

**GREEN/REFACTOR:** исправить только обнаруженные расхождения внутреннего
lifecycle; формат SSE и HTTP-слой не менять без отдельного согласования.

**Проверка:**

```sh
uv run --project backend --locked pytest backend/tests/integration/api/test_sse.py
```

## Задача 5. Архитектурная документация

**Требования:** REQ-019.

**Результат:** документация показывает `DialogEventBroker` отдельной
application-границей, описывает ответственность `InMemoryDialogEventBroker`,
обязательное constructor injection, bounded queues и отсутствие replay.
Устаревшее утверждение о том, что подписчиками владеет `AgentService`,
удаляется.

**Зависимости:** задачи 1–4.

**Предполагаемые файлы:**

- `docs/dialogs.md`;
- `docs/README.md`;
- `AGENTS.md`.

**Проверка:** ручное ревью диаграмм, внутренних контрактов, ссылок и
соответствия фактической реализации. Искусственные тесты наличия текста не
добавляются.

## Задача 6. Интеграционная проверка реализации

**Требования:** REQ-001–REQ-020 и все критерии приёмки.

**Результат:** полный набор продуктовых тестов и Ruff проходят; review
подтверждает отсутствие subscriber state в `AgentService`, публичных изменений
SSE и новых инфраструктурных зависимостей.

**Зависимости:** задачи 1–5.

**Предполагаемые файлы:** только исправления первопричин в файлах предыдущих
задач.

**Проверка:**

```sh
make test
make lint
git diff --check
```

После реализации перейти к отдельному этапу verify, записать фактические
результаты в `specs/changes/dialog-event-broker/verification.md` и только после
успешной проверки установить статус `done`.
