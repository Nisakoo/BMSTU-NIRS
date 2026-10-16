# План: аутентификация в backend — JWT, refresh-токены и пользователи в PostgreSQL

Спецификация: [spec.md](./spec.md).

## Порядок

Сначала доменное ядро без инфраструктуры (`AuthService` + in-memory фейки), затем
HTTP-слой поверх него — это сразу даёт проверяемый контракт. После этого
подключаются конфигурация, настоящие адаптеры PostgreSQL/Redis, миграции и
Compose. Документация — последней задачей, по фактической реализации.

Рискованные предположения проверяются в первых задачах:

- argon2id и PyJWT устанавливаются через `uv` и работают в `python:3.12-slim`
  (задача 1 — `uv add` и тесты хеширования);
- обязательный `AUTH_JWT_SECRET` не ломает существующие тесты конфигурации и
  bootstrap (задача 3 — тесты обновляются вместе с loader);
- формат ошибок `{"error": ...}` и `422` вместо стандартного FastAPI-ответа
  применяются только к auth-роутеру и не меняют ответы ручек диалогов
  (задача 2 — регрессия существующих API-тестов).

## Задача 1. Доменное ядро `smeshariki_ai.auth`

**Требования:** REQ-001, REQ-002, REQ-003, REQ-004, REQ-005, REQ-006, REQ-007.

**Критерии приёмки:** `AuthService` выполняет `register`, `login`,
`authenticate(access)`, `refresh`, `logout` на in-memory хранилищах с
фиксированными часами: регистрация с ролью `user` и `409` для логина,
отличающегося регистром; неотличимые ошибки входа (включая фиктивную проверку
хеша для неизвестного логина); отказ для просроченного, чужой подписи и
находящегося в blacklist access; ротация refresh и отзыв семейства при
повторном использовании; идемпотентный logout с TTL записи до `exp`; ошибка
хранилища превращается в `AuthUnavailableError`.

**Зависимости:** нет.

**Файлы:**

- `backend/pyproject.toml`, `backend/uv.lock` — `pyjwt`, `argon2-cffi`;
- `backend/src/smeshariki_ai/auth/{__init__,models,stores,passwords,tokens,service,memory,config}.py`;
- `backend/tests/unit/auth/test_auth_service.py`, `test_tokens.py`.

**Шаги:**

1. `uv add --project backend pyjwt argon2-cffi`.
2. Падающие тесты сервиса и токенов.
3. Доменные типы (`User`, `Role`, `RefreshSession`, `TokenPair`, ошибки),
   контракты `UserStore`/`RefreshSessionStore`/`TokenBlacklist`, `AuthConfig`,
   `PasswordHasher`, `TokenCodec`, `AuthService`, in-memory реализации.

**Проверка:**

```sh
uv run --project backend --locked pytest backend/tests/unit/auth
```

## Задача 2. HTTP-роутер аутентификации

**Требования:** REQ-002…REQ-007, REQ-010.

**Критерии приёмки:** пять ручек отвечают по контракту из спецификации;
лишние поля, невалидный JSON и нарушение правил дают `422`
`{"error":"invalid_fields"}` без эха введённых значений; cookie имеют `HttpOnly`,
`SameSite=Lax`, нужные `Path` и `Max-Age`, `Secure` — по настройке; logout и
неуспешный refresh сбрасывают обе cookie; `AuthUnavailableError` → `503`;
зависимость `current_user` доступна для будущих ручек; в журнале нет логинов,
паролей, токенов и `jti`. Существующие API-тесты диалогов проходят без
изменений.

**Зависимости:** задача 1.

**Файлы:**

- `backend/src/smeshariki_ai/api/auth.py` — роутер, схемы, cookie, ошибки;
- `backend/src/smeshariki_ai/api/app.py` — `create_app(..., auth_service=None)`
  подключает роутер, если сервис передан;
- `backend/src/smeshariki_ai/observability.py` — безопасное поле `user_id`;
- `backend/tests/integration/api/test_auth.py`.

**Проверка:**

```sh
uv run --project backend --locked pytest backend/tests/integration/api
```

## Задача 3. Конфигурация `auth`, `database`, `redis`

**Требования:** REQ-008.

**Критерии приёмки:** `load_config` читает `AUTH_JWT_SECRET` (обязателен,
≥ 32 байт), `AUTH_ACCESS_TTL_SECONDS` (900), `AUTH_REFRESH_TTL_SECONDS`
(2592000), `AUTH_COOKIE_SECURE` (`false`), `DATABASE_URL`, `REDIS_URL`;
некорректные значения дают ошибку валидации без текста секрета; существующие
тесты конфигурации и bootstrap обновлены и проходят.

**Зависимости:** задача 1.

**Файлы:**

- `backend/src/smeshariki_ai/config.py`;
- `backend/src/smeshariki_ai/db/config.py`, `backend/src/smeshariki_ai/cache/config.py`;
- `backend/tests/unit/test_backend_config.py`, `backend/tests/unit/test_bootstrap.py`.

**Проверка:**

```sh
uv run --project backend --locked pytest backend/tests/unit
```

## Задача 4. PostgreSQL: таблицы, миграция, адаптеры

**Требования:** REQ-007, REQ-011.

**Критерии приёмки:** Alembic-миграция `0001` создаёт `users` и
`refresh_sessions` со всеми ограничениями и индексами из спецификации;
`PostgresUserStore` и `PostgresRefreshSessionStore` выполняют контракты, а
`IntegrityError` уникального логина превращается в доменный конфликт; ошибки
подключения превращаются в `AuthUnavailableError`. Интеграционные тесты
проходят на реальном PostgreSQL при заданном `TEST_DATABASE_URL`, без него —
skip.

**Зависимости:** задачи 1, 3.

**Файлы:**

- `backend/pyproject.toml`, `backend/uv.lock` — `sqlalchemy[asyncio]`,
  `asyncpg`, `alembic`;
- `backend/src/smeshariki_ai/db/{__init__,engine,tables,stores}.py`;
- `backend/src/smeshariki_ai/db/migrations/{env.py,script.py.mako,versions/0001_users_refresh_sessions.py}`,
  `backend/alembic.ini`;
- `backend/tests/integration/db/test_postgres_stores.py`.

**Проверка:**

```sh
docker run --rm -d --name auth-pg -e POSTGRES_PASSWORD=test -p 55432:5432 postgres:17-alpine
TEST_DATABASE_URL=postgresql+asyncpg://postgres:test@127.0.0.1:55432/postgres \
  uv run --project backend --locked pytest backend/tests/integration/db
uv run --project backend --locked pytest
```

## Задача 5. Redis blacklist

**Требования:** REQ-006, REQ-007.

**Критерии приёмки:** `RedisTokenBlacklist` пишет `auth:blacklist:<jti>` с TTL
до `exp`, проверяет наличие, не пишет уже истёкшие токены; ошибки соединения
превращаются в `AuthUnavailableError`. Интеграционный тест на реальном Redis
при заданном `TEST_REDIS_URL`, без него — skip.

**Зависимости:** задачи 1, 3.

**Файлы:**

- `backend/pyproject.toml`, `backend/uv.lock` — `redis`;
- `backend/src/smeshariki_ai/cache/{__init__,blacklist}.py`;
- `backend/tests/integration/cache/test_redis_blacklist.py`.

**Проверка:**

```sh
docker run --rm -d --name auth-redis -p 56379:6379 redis:7-alpine
TEST_REDIS_URL=redis://127.0.0.1:56379/0 \
  uv run --project backend --locked pytest backend/tests/integration/cache
```

## Задача 6. Bootstrap, lifespan и Compose

**Требования:** REQ-009, REQ-012.

**Критерии приёмки:** `create_application` собирает `AuthService` с
PostgreSQL- и Redis-адаптерами и закрывает engine и Redis-клиент при
shutdown; тестовый путь допускает внедрение in-memory зависимостей. `make run`
поднимает `postgres` (volume, healthcheck), `redis` (healthcheck), `migrate`
(образ backend, `alembic upgrade head`) и `backend` после успешной миграции.
`docker/.env.example` содержит плейсхолдеры новых переменных. Сценарии
спецификации воспроизводятся `curl` через Caddy; `/login/` регистрирует,
входит и переходит на `/`.

**Зависимости:** задачи 2–5.

**Файлы:**

- `backend/src/smeshariki_ai/bootstrap.py`, `backend/src/smeshariki_ai/api/app.py`;
- `docker/compose.yaml`, `docker/Dockerfile` (копирование `alembic.ini`),
  `docker/.env.example`;
- `backend/tests/unit/test_bootstrap.py`.

**Проверка:**

```sh
make test
make lint
make run   # затем сценарии из spec.md через curl на http://127.0.0.1:8080
```

## Задача 7. Документация

**Требования:** REQ-011; решения по открытым вопросам.

**Критерии приёмки:** `docs/database.md` описывает четыре таблицы, связи,
индексы, решения схемы, статус (`dialogs`/`messages` — запланированы) и
порядок миграций; `docs/auth.md` дополнен refresh, форматом ошибок, `503`,
JWT-cookie, blacklist и ротацией, раздел «Что пока не реализовано» обновлён;
`docs/configuration.md`, `docs/logging.md`, `docs/README.md` (карта, диаграмма,
таблица компонентов), `docker/README.md`, `AGENTS.md` (PostgreSQL, Redis,
реализованная аутентификация) обновлены.

**Зависимости:** задачи 1–6.

**Файлы:** `docs/database.md`, `docs/auth.md`, `docs/configuration.md`,
`docs/logging.md`, `docs/README.md`, `docker/README.md`, `AGENTS.md`.

**Проверка:** ревью документов на соответствие реализации; автоматические
тесты для документации не добавляются.
