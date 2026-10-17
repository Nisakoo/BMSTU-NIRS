# План: постоянная история диалогов

Спецификация: [spec.md](./spec.md). Опирается на
[`dialog-ownership`](../dialog-ownership/plan.md) и
[`backend-auth-jwt`](../backend-auth-jwt/plan.md).

## Ключевые решения

- **Черновики отдельно от хранилища.** `HistoryStore` хранит только
  сохранённые диалоги. Черновики ведёт process-local `DialogDrafts` в пакете
  `dialogs`: `dialog_id` → владелец, число подписок, число запусков и время
  последней активности. `AgentService` получает его через конструктор
  (по умолчанию создаёт новый экземпляр) и сначала ищет владельца среди
  черновиков, потом в `HistoryStore`. Для черновиков PostgreSQL не нужен
  (REQ-019).
- **Истечение черновиков — ленивое**, без фоновой задачи. При каждом
  обращении к черновику проверяется его срок, а `create` удаляет все
  истёкшие черновики, чтобы ограничить рост памяти. Черновик с подпиской или
  запуском не истекает. Часы внедряются (`Callable[[], datetime]`), срок —
  константа `DRAFT_TTL = timedelta(minutes=30)`.
- **Контракт `HistoryStore`** (`dialogs/history.py`):

  ```python
  await create(dialog_id, owner_id, title, messages, now) -> None  # диалог + первые сообщения
  await owner(dialog_id) -> UUID                    # DialogNotFoundError
  await get(dialog_id) -> tuple[Message, ...]       # контекст агента
  await read(dialog_id) -> DialogTranscript         # title + StoredMessage(role, content, created_at)
  await append(dialog_id, messages, now) -> None
  await list(owner_id, limit, after: DialogCursor | None) -> tuple[DialogSummary, ...]
  await delete(dialog_id) -> None                   # DialogNotFoundError
  ```

  `DialogSummary(dialog_id, title, created_at, updated_at)` и
  `DialogCursor(updated_at, dialog_id)` — неизменяемые модели в
  `dialogs/models.py`. Время передаёт `AgentService` из внедрённых часов, а
  не берётся из `now()` базы, поэтому порядок в тестах детерминирован.
- **Пагинация.** Сервис запрашивает `limit + 1` элементов. Если пришло
  больше `limit`, курсором следующей страницы становится последний
  возвращённый элемент. Keyset-условие:
  `(updated_at, id) < (:updated_at, :id)` с сортировкой
  `ORDER BY updated_at DESC, id DESC`. HTTP-слой кодирует курсор как
  base64url (без `=`) от JSON `{"u": "<ISO 8601>", "d": "<uuid>"}`; при
  ошибке декодирования отвечает `422` в формате `RequestValidationError` с
  `loc: ["query", "cursor"]`.
- **Удаление без гонок.** `AgentService` хранит все задачи диалога
  (`dict[UUID, set[Task]]`), а не только хвост: отмена хвоста не отменяет
  предыдущие задачи. `delete_dialog`:
  1. проверяет владельца;
  2. помечает `dialog_id` как удаляемый — `submit` и `subscribe` для него
     отвечают `DialogNotFoundError`;
  3. отменяет и дожидается всех задач диалога — отменённые задачи, как и
     сейчас, публикуют `message_error`;
  4. удаляет черновик или строку в базе;
  5. вызывает `DialogEventBroker.close_dialog(dialog_id)` (события в
     очередях доставляются до закрытия, `discard_pending=False`);
  6. снимает пометку.

  Так первое сохранение черновика не может завершиться после удаления.
- **Первое сохранение.** В `_run_after` после ответа агента: если диалог ещё
  черновик, вызывается `HistoryStore.create(...)` с `make_title(request)`,
  после успеха — `drafts.discard(dialog_id)` и событие `dialog.persisted`.
  Иначе вызывается `append`. Контекст агента для черновика — `()`.
- **Postgres.** `create` — одна транзакция `INSERT dialogs` и
  `INSERT messages` (позиции 0, 1). `append` — транзакция
  `SELECT ... FOR UPDATE` строки диалога (нет строки →
  `DialogNotFoundError`), `coalesce(max(position), -1) + 1`, вставка
  сообщений, `UPDATE dialogs SET updated_at`. `delete` —
  `DELETE ... RETURNING id`; сообщения удаляет каскад. Ошибки
  SQLAlchemy/asyncpg/OS/timeout → `HistoryUnavailableError` по образцу
  `_unavailable_on_failure` из `db/stores.py`.
- **503.** Обработчик исключения `HistoryUnavailableError` на уровне
  приложения отвечает `503` `{"detail":"Dialog storage is unavailable."}`
  и пишет журнал с `error_type`, поэтому ручки не дублируют `try`.

## Порядок

Сначала доменная модель и in-memory реализации (unit), затем PostgreSQL —
самая рискованная часть: блокировки, позиции, каскады. Потом сервис, HTTP и
документация.

## Задача 1. Модели, заголовок и in-memory хранилище

**Требования:** REQ-006, REQ-009, REQ-010, REQ-011 (тип ошибки).

**Критерии приёмки:**
- `make_title(text) -> str` соответствует REQ-006: обрезка, схлопывание
  пробелов (включая `\n`, `\t`), граница ровно 60 и 61 символ, не-ASCII.
- `HistoryUnavailableError(DialogError)` в `dialogs/errors.py`.
- Контракт `HistoryStore` из «Ключевых решений»; `InMemoryHistoryStore`
  выполняет его: `create` с уже существующим id — ошибка; `append`
  нумерует сообщения и обновляет `updated_at`; `list` отдаёт только
  владельца в порядке `(updated_at, id) DESC` и учитывает `after`; `delete`
  неизвестного — `DialogNotFoundError`.
- Экспорт новых имён из `smeshariki_ai.dialogs`.

**Файлы:** `dialogs/{models,title,errors,history,__init__}.py`,
`tests/unit/dialogs/test_history.py`, `tests/unit/dialogs/test_title.py`.

**Проверка:** `uv run --project backend --locked pytest backend/tests/unit/dialogs`.

## Задача 2. Реестр черновиков

**Требования:** REQ-001, REQ-005, REQ-021 (`dialog.draft.expired`).

**Критерии приёмки:** `DialogDrafts(clock=..., ttl=DRAFT_TTL)`:
`create(owner_id) -> UUID` (UUIDv4, без коллизий с живыми черновиками),
`owner(dialog_id) -> UUID | None`, `attach/detach` подписки,
`run_started/run_finished`, `discard(dialog_id)`. Черновик истекает только
при нуле подписок и запусков дольше `ttl` с последней активности. Активностью
считается любое изменение счётчиков. Истечение журналируется
`dialog.draft.expired` с `dialog_id`. Тесты используют подменяемые часы.

**Файлы:** `dialogs/drafts.py`, `dialogs/__init__.py`,
`tests/unit/dialogs/test_drafts.py`.

**Проверка:** `uv run --project backend --locked pytest backend/tests/unit/dialogs`.

## Задача 3. Миграция `0002` и `PostgresHistoryStore`

**Требования:** REQ-003, REQ-007, REQ-008, REQ-009, REQ-011.

**Критерии приёмки:**
- `0002_dialogs_messages.py` создаёт таблицы по `docs/database.md`:
  `messages.id` — identity, `UNIQUE (dialog_id, position)`,
  `CHECK role IN ('user','assistant')`, FK с `ON DELETE CASCADE`, индекс
  `dialogs_user_id_updated_at_idx` на `(user_id, updated_at DESC)`.
  `downgrade` удаляет обе таблицы. `db/tables.py` повторяет схему.
- В `db/migrate.py` есть `downgrade(engine, revision)` рядом с `upgrade`
  (для теста отката; CLI не меняется).
- `PostgresHistoryStore` реализует контракт из задачи 1; экспорт из
  `smeshariki_ai.db`.
- Интеграционные тесты (`TEST_DATABASE_URL`, по образцу
  `tests/integration/db/test_postgres_stores.py`): `upgrade` → `downgrade
  0001` → `upgrade`; `create` и чтение через новый engine; ошибка во второй
  вставке `create` или `append` (например, нарушение `CHECK role`) не
  оставляет ни диалога, ни сообщений и не меняет `updated_at`; позиции при
  двух параллельных `append`; keyset-страницы при равных `updated_at`;
  каскад при удалении диалога и пользователя; недоступная БД (неверный порт)
  даёт `HistoryUnavailableError`.

**Файлы:** `db/migrations/versions/0002_dialogs_messages.py`,
`db/tables.py`, `db/history.py`, `db/migrate.py`, `db/__init__.py`,
`tests/integration/db/test_postgres_history.py`.

**Проверка:**
`TEST_DATABASE_URL=postgresql+asyncpg://... uv run --project backend --locked pytest backend/tests/integration/db`
на одноразовом контейнере `postgres:17-alpine`. Без переменной тесты
пропускаются, и это не считается проверкой задачи.

## Задача 4. Закрытие подписок диалога в брокере

**Требования:** REQ-015, REQ-016.

**Критерии приёмки:** абстрактный `DialogEventBroker.close_dialog(dialog_id)`.
`InMemoryDialogEventBroker` закрывает только подписки этого диалога: уже
поставленные события доставляются, затем `receive()` возвращает `None`.
Повторный вызов и вызов после `shutdown` безопасны.

**Файлы:** `application/event_broker.py`,
`tests/unit/application/test_event_broker.py` (или существующий файл тестов
брокера).

**Проверка:** `uv run --project backend --locked pytest backend/tests/unit/application`.

## Задача 5. Жизненный цикл диалога в `AgentService`

**Требования:** REQ-001…REQ-005, REQ-012…REQ-017 (application-часть),
REQ-021.

**Критерии приёмки:**
- Конструктор: `AgentService(agent, history_store, event_broker, *, drafts=None,
  clock=None)`.
- `start_dialog` создаёт черновик без обращения к `HistoryStore`.
- Владелец ищется в черновиках, затем в хранилище; чужой диалог —
  `DialogNotFoundError` и `dialog.access.denied`, как сейчас.
- `submit`/`subscribe`/`unsubscribe` и завершение задач обновляют счётчики
  черновика.
- Первый успешный запуск вызывает `create`, затем `discard`, публикует
  `message_end` после фиксации и пишет `dialog.persisted`. Неуспешный
  запуск (ошибка агента, отмена, `HistoryUnavailableError`) оставляет
  черновик, и следующий запуск снова вызывает `create`.
- `list_dialogs(user_id, limit, after) -> DialogPage(items, next_cursor)`,
  `get_dialog(dialog_id, user_id) -> DialogTranscript` (для черновика
  `title=None`, `messages=()`), `delete_dialog(dialog_id, user_id)` по
  алгоритму из «Ключевых решений» с `dialog.deleted`
  (`dialog_id`, `user_id`, `draft=True|False`).
- Задачи диалога отслеживаются множеством. `shutdown` по-прежнему отменяет
  все задачи.
- Unit-тесты на `InMemoryHistoryStore` и детерминированный fake-агент
  покрывают сценарии спецификации: сохранение после первого ответа, ошибка
  первого запуска, удаление черновика и сохранённого диалога с активным и
  ожидающим запуском (`message_error`, ничего не сохранено, другой диалог
  продолжает работу), чужой пользователь во всех новых методах, «рестарт»
  (новый сервис с тем же хранилищем), курсорные страницы 25 → 20 + 5.

**Файлы:** `application/agent_service.py`, `application/__init__.py`,
`tests/unit/application/test_agent_service.py`.

**Проверка:** `uv run --project backend --locked pytest backend/tests/unit`.

## Задача 6. HTTP-ручки и bootstrap

**Требования:** REQ-012…REQ-020, REQ-008 (bootstrap).

**Критерии приёмки:**
- `GET /api/v1/dialogs` (`limit: Query(ge=1, le=50) = 20`, `cursor: str |
  None`), `GET /api/v1/dialogs/{dialog_id}/messages`,
  `DELETE /api/v1/dialogs/{dialog_id}` → `204`. Схемы ответа — в
  `api/schemas.py`; время сериализуется как ISO 8601 UTC.
- Обработчик `HistoryUnavailableError` → `503`. Существующие ручки и формат
  их ответов не меняются.
- `bootstrap.create_application`: при `auth_service is None` сначала
  создаётся engine, а `build_agent_service` получает
  `PostgresHistoryStore(engine)`. Иначе используется `InMemoryHistoryStore`.
  `tests/unit/test_bootstrap.py` обновлён.
- Интеграционные API-тесты (`httpx.ASGITransport`): черновик не виден в
  списке до ответа и виден после; формат элементов и `next_cursor`; `422` на
  `limit=0`, `limit=51`, мусорный `cursor`; `401` раньше `404`/`422` у
  новых ручек; `404` у B и `admin` для черновика и сохранённого диалога A;
  `DELETE` во время ответа закрывает SSE после `message_error`; `403` на
  `DELETE` с `Sec-Fetch-Site: cross-site`; `503` у новых ручек и сохранённого
  диалога при хранилище, бросающем `HistoryUnavailableError`, но `201`/`202`
  для черновика; журнал без текста запроса и заголовка.

**Файлы:** `api/app.py`, `api/schemas.py`, `bootstrap.py`,
`tests/integration/api/test_dialog_history.py`, `tests/unit/test_bootstrap.py`.

**Проверка:** `uv run --project backend --locked pytest backend/tests`.

## Задача 7. Документация

**Требования:** REQ-022.

**Проверка ревью:**
- `docs/dialogs.md`: жизненный цикл с mermaid-диаграммой состояний
  «черновик → сохранён → удалён/истёк», таблица HTTP-контрактов, внутренние
  контракты, наблюдаемость. Утверждения о потере истории при рестарте и
  отсутствии API чтения удалены.
- `docs/database.md`: `dialogs` и `messages` реализованы миграцией `0002`,
  `PostgresHistoryStore`, правило «строка `dialogs` появляется вместе с
  первыми сообщениями», ссылки на артефакты.
- `docs/README.md` и `AGENTS.md` по REQ-022.

## Задача 8. Итоговая проверка (вход в verify)

- `make test` и `make lint`.
- Интеграционные DB-тесты с `TEST_DATABASE_URL` на одноразовом
  `postgres:17-alpine`.
- Runtime в `make run`, если доступен Docker и `docker/.env`: после открытия
  чата строки в `dialogs` нет; после ответа она появляется; после
  `docker compose restart backend` `curl` с cookie получает список и
  сообщения; `DELETE` удаляет диалог.
