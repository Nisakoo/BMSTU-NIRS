# Проверка: аутентификация в backend — JWT, refresh-токены и пользователи в PostgreSQL

## Итог

Изменение успешно прошло verify 2026-10-16. В backend добавлены пакет
`smeshariki_ai.auth`, HTTP-роутер аутентификации, адаптеры PostgreSQL и Redis,
Alembic-миграция `0001`, подконфиги `auth`/`database`/`redis` и сервисы
`postgres`, `redis`, `migrate` в Compose. Frontend не менялся.

## Проверка требований

| Требование | Доказательство | Результат |
| --- | --- | --- |
| REQ-001 | `AuthService` и контракты в `auth/`; модуль не импортирует FastAPI, SQLAlchemy и redis-py; 12 тестов `test_auth_service.py` на in-memory хранилищах | Пройдено |
| REQ-002 | `test_register_creates_user_role_and_hashes_password`, `test_register_rejects_login_that_differs_only_by_case`, HTTP `test_register_conflict_is_case_insensitive`; Compose: `Krosh` → `201`, `kROSH` → `409` | Пройдено |
| REQ-003 | `test_login_failures_are_indistinguishable_and_always_verify_hash` (хеш проверяется и для неизвестного логина), HTTP `test_login_errors_are_identical` (байт-в-байт одинаковые тела), `test_login_sets_http_only_cookies` | Пройдено |
| REQ-004 | `test_authenticate_rejects_expired_foreign_and_garbage_tokens`, `test_authenticate_returns_current_role_from_store`, 7 тестов `test_tokens.py` (подмена claims, `alg=none`, `exp` по внедрённым часам) | Пройдено |
| REQ-005 | `test_refresh_rotates_token_and_detects_reuse` (сервис и HTTP); интеграционный `test_refresh_store_rotation_revocation_and_cascade` на PostgreSQL; Compose: R1 → `200`, повтор R1 → `401`, R2 → `401` | Пройдено |
| REQ-006 | `test_logout_blacklists_access_until_expiry_and_revokes_refresh`, `test_logout_is_idempotent_...`, HTTP `test_logout_blacklists_copied_access_token`; Redis `test_blacklist_entry_lives_until_token_expiry` (TTL ≤ остатку жизни); Compose: копия access после logout → `401` | Пройдено |
| REQ-007 | `test_unavailable_blacklist_fails_closed`, HTTP `test_unavailable_storage_returns_503`, `test_unreachable_database_is_unavailable`, `test_unreachable_redis_is_unavailable`; Compose: `/users/me` при остановленном Redis → `503`, после старта → `200` | Пройдено |
| REQ-008 | 6 новых тестов `test_backend_config.py`: значения, defaults, 9 вариантов невалидного environment без утечки секрета в ошибке, `repr` без секретов | Пройдено |
| REQ-009 | `test_create_application_wires_auth_and_closes_infrastructure` (передаются ровно `config.database`/`config.redis`, engine и Redis закрываются в lifespan), `test_create_application_accepts_explicit_auth_service`; HTTP `test_dialog_routes_keep_their_error_format`; Compose: `POST /api/v1/dialogs` → `201` без аутентификации | Пройдено |
| REQ-010 | HTTP `test_logs_do_not_contain_credentials_or_tokens`; Compose: в журнале backend нет логина, паролей, access-токена, JWT-секрета и пароля PostgreSQL, есть `auth.*` события с `user_id` | Пройдено |
| REQ-011 | Интеграционные тесты PostgreSQL после `upgrade head`; `\d users`, `\d refresh_sessions` в Compose совпадают со схемой спецификации, `alembic_version = 0001`; ревью `docs/database.md` | Пройдено |
| REQ-012 | `docker compose up --build`: `postgres` и `redis` healthy, `migrate` завершился с кодом 0, `backend` стартовал после него | Пройдено |

## Критерии приёмки

| Критерий | Результат |
| --- | --- |
| Compose поднимает все сервисы, миграция применяется автоматически | Пройдено; проверено `docker compose up --build -d` с `APP_PORT=18080`, что эквивалентно `make run` без режима foreground |
| Сценарии спецификации воспроизводятся `curl` через Caddy | Пройдено: регистрация, конфликт, лишнее поле, неверный пароль и неизвестный логин, вход и атрибуты cookie, `/users/me`, ротация и reuse detection, logout и blacklist, logout без сессии, Redis недоступен |
| `/login/` работает без правок frontend | Пройдено: немодифицированный `frontend/src/auth-api.js` в Node против Compose стека — `unauthorized` до входа, регистрация, `login_taken`, `invalid_credentials`, вход, `me`, logout, `unauthorized` после; `/login/` отдаёт `200`; редирект и UI покрыты существующими 52 frontend-тестами |
| В журнале нет логинов, паролей, токенов и cookie | Пройдено (REQ-010) |
| Документация обновлена | Пройдено: новая `docs/database.md`; `docs/auth.md` (refresh, формат ошибок, `503`, JWT-cookie, blacklist, ротация), `docs/configuration.md`, `docs/logging.md`, `docs/README.md`, `docker/README.md`, `frontend/README.md`, `AGENTS.md` |
| `make test` и `make lint` | Пройдено: frontend 52/52; backend 206 passed, 7 skipped (интеграционные без `TEST_DATABASE_URL`/`TEST_REDIS_URL`); Ruff без замечаний |

## Команды

```sh
make test
make lint
docker run --rm -d --name auth-pg -e POSTGRES_PASSWORD=test -p 55432:5432 postgres:17-alpine
TEST_DATABASE_URL=postgresql+asyncpg://postgres:test@127.0.0.1:55432/postgres \
  uv run --project backend --locked pytest backend/tests/integration/db     # 4 passed
docker run --rm -d --name auth-redis -p 56379:6379 redis:7-alpine
TEST_REDIS_URL=redis://127.0.0.1:56379/0 \
  uv run --project backend --locked pytest backend/tests/integration/cache  # 3 passed
APP_PORT=18080 AUTH_JWT_SECRET=... POSTGRES_PASSWORD=... \
  docker compose --env-file docker/.env -f docker/compose.yaml up --build -d
```

## Отклонения от плана

- Вместо `backend/alembic.ini` миграции запускаются командой
  `python -m smeshariki_ai.db.migrate`: так URL приходит из `load_config`, и
  правило «environment читает только `load_config`» сохраняется.
- `Makefile` запускает `pytest backend`: без аргумента pytest из корня не видел
  `backend/pyproject.toml`, и `asyncio_mode = "auto"` не применялся к async
  тестам.
- В `compose.yaml` добавлено явное имя проекта `smeshariki-ai`. Раньше имя
  выводилось из каталога `docker/` и совпадало с другим локальным проектом,
  у которого тоже есть сервис `postgres` и том `docker_postgres-data`.

## Известные ограничения

- Интеграционные тесты PostgreSQL и Redis в `make test` пропускаются без
  `TEST_DATABASE_URL` и `TEST_REDIS_URL`; они выполнены вручную командами выше.
- Визуальная проверка `/login/` в браузере не выполнялась: frontend не менялся,
  совместимость контракта подтверждена реальным клиентом.
- Автоматический refresh во frontend, защита чата, создание администратора и
  rate limiting — вне изменения (см. «Границы» спецификации).
- После смены имени Compose-проекта ранее запущенные контейнеры старого проекта
  `docker` (`docker-backend-1`, `docker-frontend-1`, `docker-caddy-1`) нужно
  остановить вручную, иначе они продолжат занимать порт `8080`.
