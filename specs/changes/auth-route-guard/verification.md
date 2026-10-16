# Verification: защита ручек диалогов, редиректы и создание администратора

Спецификация: [spec.md](./spec.md), план: [plan.md](./plan.md).
Дата проверки: 2026-10-16, ветка `feat/auth-guard` от `main` (`fca3ff6`).

## Итоговые команды

| Команда | Результат |
| --- | --- |
| `make lint` | `All checks passed!`, 77 файлов отформатированы |
| `make test` | frontend: 80 passed, 0 failed; backend: 232 passed, 7 skipped |
| `npm --prefix frontend run build` | успешная сборка entry `main`, `admin`, `login` и общего чанка `auth-session` |

7 пропущенных backend-тестов — существующие интеграционные тесты PostgreSQL и
Redis, которые требуют `TEST_DATABASE_URL`/`TEST_REDIS_URL`; изменение их не
затрагивает и тесты не отключает.

## Требования

| Требование | Проверка | Результат |
| --- | --- | --- |
| REQ-001 | `test_auth.py::test_dialog_routes_require_access_cookie` и `test_dialog_routes_reject_invalid_access_token` (5 запросов каждый), `test_dialog_routes_reject_blacklisted_access_token`; runtime `curl` | Выполнено |
| REQ-002 | `test_dialog_routes_fail_closed_when_storage_is_unavailable`, `test_dialog_routes_fail_closed_without_auth_service` | Выполнено |
| REQ-003 | `test_authenticated_dialog_routes_keep_their_behavior`, параметризованный `test_dialog_routes_keep_their_error_format`, существующие `test_dialogs.py`, `test_sse.py`, `test_litellm_provider.py` с аутентифицированным клиентом | Выполнено |
| REQ-004 | Случаи `bad-id` и `bad-json` в тестах REQ-001; runtime: гость с некорректным JSON получает `401` | Выполнено |
| REQ-005 | `test_auth.py` (открытые ручки аутентификации), `test_agent_test.py` и `test_dialog_routes_fail_closed_without_auth_service` (`/agent_test` → `200`) | Выполнено |
| REQ-006 | `auth-api.test.js`: `refresh posts without a body…`, коды `401`/`503`, сетевой сбой | Выполнено |
| REQ-007 | `auth-session.test.js`: 6 тестов на три исхода и единственный `refresh` | Выполнено |
| REQ-008, REQ-009 | `ui.test.js`: `a guest is redirected…`, `an expired access token is renewed…` | Выполнено |
| REQ-010 | `ui.test.js`: `an unavailable auth backend keeps the page and retries the check` | Выполнено |
| REQ-011 | `ui.test.js`: четыре теста `401` у создания диалога и отправки, включая отсутствие дублирования реплики | Выполнено |
| REQ-012 | `ui.test.js`: `an SSE error without a session…`, `a closed SSE connection… reopened once until ready`, `…while the browser reconnects…`; `agent-api.test.js`: `isClosed` | Выполнено |
| REQ-013 | `admin-ui.test.js`: 5 тестов guard для `admin`, `user`, гостя, refresh и недоступности | Выполнено |
| REQ-014, REQ-015 | `login-ui.test.js`: переходы по роли при открытии, после `refresh`, после входа и регистрации | Выполнено |
| REQ-016…REQ-019 | `tests/unit/auth/test_create_admin.py` (9 тестов); runtime в Compose: создание, занятый логин в другом регистре, неверный логин, вход администратора | Выполнено |
| REQ-020 | runtime: `POST /users` с `"role":"admin"` → `422`; регистрация по-прежнему создаёт `user` (`test_auth.py`) | Выполнено |
| REQ-021 | Ревью: `docs/auth.md`, `docs/dialogs.md`, `docs/README.md`, `frontend/README.md`, `docker/README.md`, `AGENTS.md` | Выполнено |

## Runtime-проверка

Изолированный Compose-проект `smeshariki-verify` (отдельные тома, порт
`18080`, временный env-файл из `docker/.env.example`); после проверки удалён
командой `down -v`.

- без cookie: `POST /api/v1/dialogs`, `POST …/messages` с некорректным JSON и
  `GET …/events` → `401 {"error":"unauthorized"}`;
- после регистрации и входа: `POST /api/v1/dialogs` → `201`, неизвестный
  диалог → `404 {"detail":"Dialog not found."}`;
- `/`, `/admin/`, `/login/` через Caddy → `200`;
- `python -m smeshariki_ai.create_admin --login Sovunya` в контейнере
  `migrate` → «Администратор «Sovunya» создан.», код `0`; повтор для `sovunya` →
  «уже занят», код `1`; логин `x` → сообщение о правилах до запроса пароля;
- вход `sovunya` → `200`, `/users/me` → `"role":"admin"`;
- пароль администратора не встречается в журнале backend.

## Известные ограничения

- Ввод пароля проверен через stdin с `docker compose run -T`, так как в среде
  проверки нет TTY; поэтому Python выводил `GetPassWarning`. Цель
  `make create-admin` запускает `run` без `-T` и в обычном терминале
  использует скрытый ввод `getpass`. Сама цель проверена `make -n` и проверкой
  отсутствия `LOGIN`; полный запуск не выполнялся, чтобы не менять локальный
  `docker/.env` и тома основного проекта.
- Редиректы в браузере проверены Node-тестами с fake `fetch`, `EventSource` и
  `location`; ручная проверка в реальном браузере не выполнялась.
- `/agent_test` не проксируется Caddy (поведение до изменения) и доступен
  только напрямую через backend.
- Проверка роли на `/admin/` скрывает demo-данные, но не защищает данные;
  диалоги не привязаны к пользователю — см. «Что пока не реализовано» в
  [`docs/auth.md`](../../../docs/auth.md).
