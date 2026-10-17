# План: владение диалогами

Спецификация: [spec.md](./spec.md). Выполняется после
[`auth-hardening`](../auth-hardening/plan.md).

## Порядок

Сначала хранилище и сервис (unit), затем HTTP-слой и перевод существующих
интеграционных тестов на владельца. Документация — последней.

## Задача 1. Владелец в `HistoryStore` и `AgentService`

**Требования:** REQ-001, REQ-002, REQ-004, REQ-005.

**Критерии приёмки:**
- `HistoryStore.create(owner_id: UUID) -> UUID`; новый абстрактный метод
  `owner(dialog_id) -> UUID` (бросает `DialogNotFoundError`), либо
  эквивалент; `InMemoryHistoryStore` хранит владельца рядом с историей под тем
  же lock.
- `AgentService.start_dialog(user_id)`, `submit(dialog_id, user_id, request)`,
  `subscribe(dialog_id, user_id)`: при несовпадении владельца бросают
  `DialogNotFoundError`, не создают задачу и подписку; журналируют
  `dialog.access.denied` с `dialog_id`, `user_id`, `outcome="foreign"`.
- `_run_after` и запись истории не меняются.

**Файлы:** `backend/src/smeshariki_ai/dialogs/history.py`,
`backend/src/smeshariki_ai/application/agent_service.py`,
`backend/tests/unit/dialogs/test_history.py`,
`backend/tests/unit/application/test_agent_service.py`.

**Проверка:** `uv run --project backend --locked pytest backend/tests/unit/dialogs backend/tests/unit/application`.

## Задача 2. HTTP-слой

**Требования:** REQ-002, REQ-003.

**Критерии приёмки:** ручки `start_dialog`, `submit_message`,
`stream_dialog_events` получают `User` через `Depends(current_user)` (FastAPI
кэширует зависимость, повторной проверки токена нет) и передают `user.id`;
`DialogNotFoundError` по-прежнему даёт `404` `Dialog not found.`. Тестовый
`StaticAuthService` в `api_auth_support.py` поддерживает двух пользователей
(например, по значению cookie), чтобы тесты могли проверить чужой диалог.
Интеграционные тесты: B получает `404` у `messages` и `events` для диалога A,
администратор тоже; история A не меняется; agent fake не вызывается.

**Файлы:** `backend/src/smeshariki_ai/api/app.py`,
`backend/tests/integration/api/{api_auth_support,test_dialogs,test_sse}.py`.

**Проверка:** `uv run --project backend --locked pytest backend/tests/integration/api`.

## Задача 3. Документация и итоговая проверка

**Требования:** REQ-006.

**Проверка:** ревью `docs/dialogs.md`, `docs/auth.md`, `AGENTS.md`,
`docs/README.md`; `make test`; `make lint`; runtime в `make run`: чат
работает, `curl` с cookie второго пользователя к чужому `dialog_id` даёт
`404`.
