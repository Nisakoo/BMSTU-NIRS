# План: постоянная история диалогов пользователя

Спецификация: [spec.md](./spec.md).

## Порядок

Сначала доменный контракт `HistoryStore` с владельцем и названием, его
in-memory реализация и `AgentService` — это фиксирует поведение и проверяется
быстрыми модульными тестами. Затем HTTP-ручки на in-memory хранилище. После
этого рискованная часть — миграция и SQL-адаптер на реальной PostgreSQL, и
подключение в bootstrap. Документация и ручная проверка рестарта — последними.

## Решения

- Контракт `HistoryStore` (пакет `dialogs`):
  `create(owner_id) -> UUID`, `get(dialog_id, owner_id) -> tuple[Message, ...]`,
  `append(dialog_id, messages)`, `list_dialogs(owner_id, limit) ->
  tuple[DialogSummary, ...]`, `transcript(dialog_id, owner_id) ->
  DialogTranscript`. Чужой и несуществующий диалог одинаково дают
  `DialogNotFoundError`; сбой хранилища — `DialogStoreUnavailableError`.
- Функция `dialog_title(text)` в пакете `dialogs` реализует REQ-005; `append`
  задаёт название из первого сообщения `user`, только если оно ещё `NULL`.
- `AgentService` получает `user_id` во всех операциях диалога и передаёт его
  хранилищу; фоновый запуск читает историю с тем же владельцем.
- Ручки получают пользователя через `Depends(current_user)` (FastAPI кэширует
  зависимость, повторной проверки токена нет). `DialogStoreUnavailableError` →
  `503` `{"detail":"Agent service is unavailable."}`.
- Время в in-memory хранилище берётся из инжектируемых часов, в PostgreSQL — из
  `now()` транзакции.

## Задача 1. Контракт хранилища, in-memory реализация и сервис

**Требования:** REQ-003, REQ-004, REQ-005, REQ-007, REQ-009, REQ-010.

**Критерии приёмки:** in-memory хранилище проверяет владельца, задаёт и не
меняет название, атомарно добавляет пару, обновляет `updated_at`, список
фильтрует пустые диалоги, сортирует от новых и ограничивает лимитом;
`AgentService` передаёт владельца во всех операциях, не сохраняет историю при
ошибке агента.

**Файлы:** `backend/src/smeshariki_ai/dialogs/{__init__,errors,history,models}.py`,
`backend/src/smeshariki_ai/application/agent_service.py`,
`backend/tests/unit/dialogs/test_history.py`,
`backend/tests/unit/application/test_agent_service.py`.

**Проверка:** `uv run --project backend --locked pytest backend/tests/unit`.

## Задача 2. HTTP-ручки списка и истории

**Требования:** REQ-007…REQ-012.

**Критерии приёмки:** `GET /api/v1/dialogs` и
`GET /api/v1/dialogs/{id}/messages` возвращают контракт REQ-009/REQ-010;
чужой диалог даёт `404` на всех четырёх ручках диалога; гость — `401` раньше
`404`/`422`; недоступное хранилище — `503`; прежние ручки сохраняют коды и
тела.

**Файлы:** `backend/src/smeshariki_ai/api/{app,schemas}.py`,
`backend/tests/integration/api/test_dialogs.py`,
`backend/tests/integration/api/test_dialog_history.py`,
`backend/tests/integration/api/api_auth_support.py` (второй пользователь).

**Проверка:** `uv run --project backend --locked pytest backend/tests/integration/api`.

## Задача 3. Миграция, PostgreSQL-адаптер и bootstrap

**Требования:** REQ-001, REQ-002, REQ-004, REQ-006, REQ-012, REQ-013.

**Критерии приёмки:** миграция `0002` создаёт таблицы, индексы и ограничения
схемы; `PostgresHistoryStore` проходит те же сценарии, что in-memory, плюс
каскадное удаление и лимит 50; ошибки БД превращаются в
`DialogStoreUnavailableError`; production bootstrap использует
`PostgresHistoryStore` на общем engine, а тестовая сборка с внешним
`auth_service` — in-memory.

**Файлы:** `backend/src/smeshariki_ai/db/{tables,history,__init__}.py`,
`backend/src/smeshariki_ai/db/migrations/versions/0002_dialogs_messages.py`,
`backend/src/smeshariki_ai/bootstrap.py`,
`backend/tests/integration/db/test_postgres_history.py`,
`backend/tests/unit/test_bootstrap.py`.

**Проверка:** временный контейнер `postgres:17-alpine` и
`TEST_DATABASE_URL=… uv run --project backend --locked pytest backend/tests/integration/db`;
затем `make test` и `make lint`.

## Задача 4. Документация

**Требования:** критерий приёмки по документации.

**Файлы:** `docs/dialogs.md`, `docs/database.md`, `docs/README.md`,
`AGENTS.md` (раздел о реализованных диалогах: хранилище больше не in-memory).

**Проверка:** ревью.

## Задача 5. Ручная проверка в Compose

**Требования:** REQ-001, REQ-006.

**Проверка:** `make run`; регистрация, диалог, `GET /api/v1/dialogs`;
`docker compose restart backend`; список и история на месте, новое сообщение
продолжает историю.
