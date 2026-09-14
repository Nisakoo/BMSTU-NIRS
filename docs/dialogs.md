# Диалоги и HTTP API

[← Глобальный каталог](./README.md)

Диалоговый слой связывает HTTP API с независимым runtime агента. Прикладная
координация находится в `application`, хранение истории — в `dialogs`, а
FastAPI-маршруты только валидируют HTTP-ввод и преобразуют ошибки.

## Где находится реализация

- [`application/agent_service.py`](../backend/src/smeshariki_ai/application/agent_service.py)
  — очередь запусков и `AgentService`;
- [`dialogs/history.py`](../backend/src/smeshariki_ai/dialogs/history.py) —
  контракт истории и in-memory реализация;
- [`api/app.py`](../backend/src/smeshariki_ai/api/app.py) — HTTP-маршруты и
  shutdown lifecycle;
- [`api/schemas.py`](../backend/src/smeshariki_ai/api/schemas.py) — схемы HTTP-
  запросов и ответов;
- [`bootstrap.py`](../backend/src/smeshariki_ai/bootstrap.py) — сборка готовых
  зависимостей приложения.

## Внутренние контракты

```python
await AgentService.start_dialog() -> UUID
await AgentService.submit(dialog_id: UUID, request: UserRequest) -> None
await AgentService.shutdown() -> None
```

`start_dialog` создаёт пустую историю и возвращает UUIDv4. Возврат из `submit`
означает только то, что фоновая задача создана в текущем процессе; метод не ждёт
ответа агента.

Для одного `dialog_id` сервис хранит хвост цепочки `asyncio.Task`: следующий
запуск ожидает предыдущий и только затем читает обновлённую историю. Разные
диалоги имеют независимые цепочки и могут выполняться параллельно. Очередь не
ограничена по длине и не сохраняется после перезапуска.

```python
await HistoryStore.create() -> UUID
await HistoryStore.get(dialog_id: UUID) -> tuple[Message, ...]
await HistoryStore.append(
    dialog_id: UUID,
    messages: Sequence[Message],
) -> None
```

`get` возвращает неизменяемый снимок. `append` атомарно добавляет группу
сообщений. После успешного запуска сервис сохраняет одной операцией только
пользовательское и финальное сообщения ассистента. При ошибке агента история не
меняется; tool calls и tool results в историю диалога не попадают.

## Поток сообщения

```mermaid
sequenceDiagram
    participant Client as HTTP-клиент
    participant API as FastAPI
    participant Service as AgentService
    participant Task as Фоновая цепочка
    participant Agent
    participant History as HistoryStore

    Client->>API: POST /dialogs/{dialog_id}/messages
    API->>Service: submit(dialog_id, request)
    Service->>Task: создать задачу после хвоста диалога
    Service-->>API: постановка завершена
    API-->>Client: 202 Accepted, пустое тело
    Task->>History: get(dialog_id)
    Task->>Agent: run(history, request)
    Agent-->>Task: AgentResponse
    Task->>History: append(user, assistant)
```

## HTTP-контракты

Базовый префикс API — `/api/v1`.

| Запрос | Успешный ответ | Ошибки |
| --- | --- | --- |
| `POST /api/v1/dialogs` без тела | `201 Created`, `Location: /api/v1/dialogs/<uuid>`, JSON `{"dialog_id":"<uuid>"}` | `503 Service Unavailable`, если сервис больше не принимает запросы |
| `POST /api/v1/dialogs/{dialog_id}/messages` с JSON `{"request":"<непустой текст>"}` | Немедленный `202 Accepted` с пустым телом после создания фоновой задачи | `404 Not Found` для неизвестного диалога; `422 Unprocessable Entity` для некорректного UUID, пустого текста или лишних полей; `503 Service Unavailable`, если задачу нельзя принять |

`dialog_id` всегда передаётся в URL и не является средством авторизации. Cookie
для выбора диалога не создаются и не читаются.

Первая версия не возвращает через HTTP результат agent loop, историю, прогресс
или ошибку фоновой задачи. В ней также нет SSE, streaming response и CORS.

## Наблюдаемость и lifecycle

Сервис журналирует создание диалога, принятие запроса, начало и завершение
фонового запуска, сохранение истории, отмену и тип ошибки с привязкой к
`dialog_id`. Вместе с событиями runtime это позволяет увидеть каждую итерацию и
статус инструмента. Текст запроса, история, ответы, tool payload, секреты и текст
исключения не журналируются.

При штатном shutdown сервис прекращает принимать новые запросы, отменяет все
отслеживаемые фоновые задачи и ожидает их завершения. История и очередь находятся
только в памяти процесса и после перезапуска теряются.

## Где искать подробности

- [спецификация](../specs/changes/agent-dialog-api/spec.md);
- [план](../specs/changes/agent-dialog-api/plan.md);
- [результат проверки](../specs/changes/agent-dialog-api/verification.md);
- [запуск и тестовые HTTP-запросы](../docker/README.md).
