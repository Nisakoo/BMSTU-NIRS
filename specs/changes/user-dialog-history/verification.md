# Verification: постоянная история диалогов пользователя

Спецификация: [spec.md](./spec.md), план: [plan.md](./plan.md).
Дата проверки: 2026-10-17, ветка `main` (рабочая копия).

## Итоговые команды

| Команда | Результат |
| --- | --- |
| `make lint` | `All checks passed!`, 91 файл отформатирован |
| `make test` | frontend: 98 passed, 0 failed; backend: 279 passed, 17 skipped |
| `TEST_DATABASE_URL=… pytest backend/tests/integration/db` на временном `postgres:17-alpine` | 14 passed (6 новых тестов `PostgresHistoryStore` и 8 существующих) |
| `make run` (пересборка Compose), `make migrate` через сервис `migrate` | миграция `0002` применена, `alembic_version = 0002`, таблицы `dialogs`, `messages` созданы рядом с существующими данными аутентификации |

17 пропусков в `make test` — интеграционные тесты PostgreSQL и Redis без
`TEST_DATABASE_URL`/`TEST_REDIS_URL`; тесты PostgreSQL отдельно запущены и
прошли на временной базе, контейнер после проверки удалён.

## Требования

| Требование | Проверка | Результат |
| --- | --- | --- |
| REQ-001 | `test_postgres_history.py` (миграция в фикстуре, каскад, уникальные позиции при параллельной записи); runtime `\dt` и `alembic_version` | Выполнено |
| REQ-002 | `test_bootstrap.py::test_production_application_keeps_history_in_postgres`; `test_history.py` для `InMemoryHistoryStore` | Выполнено |
| REQ-003 | `test_history.py::test_create_returns_unique_uuid4_with_empty_history`; `test_dialog_history.py` (владелец — текущий пользователь); прежний `test_create_dialog_returns_201_uuid4_and_location` | Выполнено |
| REQ-004 | `test_history.py::test_append_is_atomic_ordered_and_isolated_between_dialogs`; `test_postgres_history.py::test_history_is_ordered_titled_and_owned`, `test_list_filters_orders_and_limits` (`updated_at`); `test_agent_service.py` (история не меняется при ошибке агента и при сбое сохранения) | Выполнено |
| REQ-005 | `test_history.py::test_dialog_title_collapses_whitespace_and_truncates`, `test_first_user_message_sets_the_title_once`; PostgreSQL-вариант в `test_history_is_ordered_titled_and_owned` | Выполнено |
| REQ-006 | Runtime: после `docker compose restart backend` список и сообщения возвращены, новое сообщение «Как звали героев в предыдущей истории?» получило ответ «Крош и Ёжик.», в диалоге 4 сообщения | Выполнено |
| REQ-007 | `test_dialog_history.py::test_foreign_dialog_is_not_found_on_every_dialog_route`; `test_agent_service.py::test_foreign_dialog_is_not_found_for_submit_and_subscribe`; runtime: второй пользователь получил `404` и пустой список | Выполнено |
| REQ-008 | `test_dialog_history.py::test_guest_gets_401_before_validation`; прежние тесты защиты ручек | Выполнено |
| REQ-009 | `test_dialog_history.py::test_list_is_empty_for_a_new_user`, `test_answered_dialog_is_listed_and_its_messages_are_returned` (ISO 8601 UTC, набор полей, фильтр пустых); лимит 50 — `test_list_is_limited_to_fifty_dialogs`, `test_list_returns_at_most_fifty` | Выполнено |
| REQ-010 | `test_answered_dialog_is_listed_and_its_messages_are_returned`, `test_new_dialog_has_no_title_and_no_messages` | Выполнено |
| REQ-011 | Существующие `test_dialogs.py`, `test_sse.py`, `test_litellm_provider.py` проходят с прежними кодами, телами и событиями | Выполнено |
| REQ-012 | `test_dialog_history.py::test_unavailable_store_returns_safe_503`, `test_unavailable_store_on_submit_returns_safe_503`; `test_postgres_history.py::test_unreachable_database_is_unavailable`; `test_agent_service.py::test_failed_save_publishes_error_and_keeps_history` | Выполнено |
| REQ-013 | Ревью: новые события журнала не добавлялись, `user_id` и названия не логируются; engine с `hide_parameters=True`; прежний `test_json_logs_link_http_request_and_background_run` проходит | Выполнено |

## Документация

Ревью: `docs/dialogs.md` (контракты `AgentService`/`HistoryStore`, новые
ручки, владение, `503`), `docs/database.md` (таблицы реализованы, транзакция
добавления), `docs/README.md` (новая строка компонента, раздел
«Что пока не реализовано»), `AGENTS.md` (раздел о диалогах и аутентификации).

## Известные ограничения

- Очередь фоновых запусков и SSE-события по-прежнему находятся в памяти
  процесса: ответ, который генерировался в момент рестарта, теряется.
- Удаление, переименование диалогов и пагинация списка не реализованы
  (по спецификации).
- Во время runtime-проверки в локальной базе Compose созданы тестовые
  пользователи `sdd_krosh` и `sdd_nyusha` с одним диалогом.
