# Проверка: постоянная история диалогов

Спецификация: [spec.md](./spec.md), план: [plan.md](./plan.md).
Дата: 2026-10-17. Ветка `feat/dialog-history`.

## Команды

| Команда | Результат |
| --- | --- |
| `TEST_DATABASE_URL=postgresql+asyncpg://…@127.0.0.1:55433/test make test` (одноразовый `postgres:17-alpine`) | frontend Node-тесты прошли; backend: 405 passed, 8 skipped |
| `TEST_DATABASE_URL=… uv run --project backend --locked pytest backend/tests/integration/db` | 18 passed, из них 11 новых в `test_postgres_history.py` |
| `make lint` | `All checks passed!`, 103 files already formatted |

Все 8 пропусков — Redis-тесты (`TEST_REDIS_URL` не задан). Они не относятся к
этому изменению.

## Требования

| Требование | Как подтверждено |
| --- | --- |
| REQ-001, REQ-002 | Unit `test_start_dialog_creates_a_draft_without_touching_history_store`; API-тесты `test_dialog_history.py`; runtime: после `POST /dialogs` список пуст, `dialogs` пуста |
| REQ-003 | Unit `test_first_success_persists_draft_with_title_and_clock_time`; runtime: диалог появился в списке после `message_end` |
| REQ-004 | Unit `test_failed_first_run_keeps_draft_and_next_run_is_first_again`, `test_storage_failure_on_first_save_keeps_draft_and_reports_error` |
| REQ-005 | Unit `test_drafts.py`, `test_idle_draft_expires_but_subscription_or_run_keeps_it` |
| REQ-006 | Unit `test_title.py`; runtime: пробелы и `\n` в заголовке нормализованы |
| REQ-007 | Integration `test_postgres_history.py`: upgrade → downgrade `0001` → upgrade; runtime: `alembic_version = 0002` после сервиса `migrate` |
| REQ-008 | Integration: чтение через новый engine; unit `test_saved_dialog_survives_service_restart_and_gives_agent_context`; runtime: после `docker compose restart backend` `GET .../messages` вернул обе реплики |
| REQ-009 | Integration: атомарность при нарушении `CHECK`, позиции при параллельных `append`; unit `test_title_is_fixed_by_first_request_and_updated_at_moves` |
| REQ-010 | Unit `test_history.py` для `InMemoryHistoryStore` |
| REQ-011 | Integration: недоступная БД даёт `HistoryUnavailableError` |
| REQ-012, REQ-013 | Unit `test_list_dialogs_*`; integration keyset при равных `updated_at`; API: формат, `next_cursor`, `422` на `limit`/`cursor` |
| REQ-014 | Unit `test_get_dialog_of_draft_is_empty_and_foreign_access_is_hidden`; API-тесты |
| REQ-015, REQ-016 | Unit `test_delete_draft_cancels_runs_and_stores_nothing`, `test_delete_saved_dialog_removes_rows_and_cancels_runs`, `test_delete_closes_subscriptions_of_the_dialog_only`, регрессионные `test_delete_before_run_starts_still_reports_error_to_subscribers` и `test_delete_after_first_save_committed_removes_the_stored_dialog`; API: SSE закрывается после `message_error`; runtime: `DELETE` → `204`, затем `404`, строк `messages` 0 |
| REQ-017 | Unit и API: `404` для чужого черновика и диалога, в том числе для `admin`; `dialog.access.denied` |
| REQ-018 | API-тест; runtime: `DELETE` с `Sec-Fetch-Site: cross-site` → `403` |
| REQ-019 | API: `503` при `HistoryUnavailableError`, `201`/`202` для черновика; `test_storage_failure_on_delete_is_reported_and_dialog_is_kept` |
| REQ-020 | Существующие `test_dialogs.py`, `test_sse.py`, `test_security.py` проходят |
| REQ-021 | Unit-тесты журнала (`dialog.deleted`, `dialog.persisted`, `dialog.draft.expired`) без пользовательского текста; runtime: в логах backend нет текста запроса |
| REQ-022 | Ревью `docs/dialogs.md` (жизненный цикл с диаграммой, HTTP- и внутренние контракты), `docs/database.md` (`0002`, `PostgresHistoryStore`), `docs/README.md`, `AGENTS.md` |

## Runtime-проверка

Проверка шла через `docker compose` с локальным `docker/.env` и `curl` на
`http://127.0.0.1:8080`:

1. Зарегистрирован и залогинен пользователь.
2. После `POST /dialogs` список пуст.
3. Отправлен запрос в SSE. Пришли `ready`, `message_start`, `message_delta` ×103 и `message_end`, после чего диалог появился в списке с заголовком.
4. После рестарта backend сообщения читаются.
5. `DELETE` вернул `204`, затем `messages` вернул `404`, межсайтовый `DELETE` — `403`, список пуст.

## Исправления на этапе verify

При ревью нашлись два нарушения REQ-016 в `AgentService.delete_dialog`. Оба
исправлены, на каждое добавлен регрессионный тест:

- задача, отменённая до первого шага, не публиковала `message_error`.
  Теперь сервис публикует ошибку сам;
- отмена между фиксацией первого сохранения и `drafts.discard` оставляла
  строку в базе. Теперь при удалении черновика с отменёнными запусками сервис
  удаляет и возможную строку в базе.

## Ограничения

- Черновики, очередь запусков и SSE-подписки живут в памяти одного процесса.
- `AGENTS.md` по-прежнему упоминает «пустой `ToolRegistry`», хотя bootstrap
  регистрирует `GetContextTool`. Расхождение было до этого изменения и в его
  объём не входит.
- В локальной базе остался тестовый пользователь `verify_*` из runtime-проверки.
