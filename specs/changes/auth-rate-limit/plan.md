# План: ограничение частоты входа и одновременный refresh

Спецификация: [spec.md](./spec.md). Выполняется после
[`auth-hardening`](../auth-hardening/plan.md) (порядок `403`→`415` уже есть)
и [`dialog-ownership`](../dialog-ownership/plan.md).

## Порядок

Рискованная часть — определение IP за Caddy, поэтому она идёт первой и
проверяется в Compose до написания лимитов. Затем доменный ограничитель,
Redis-адаптер, HTTP, argon2, frontend. Документация — последней.

## Задача 1. Доверие `X-Forwarded-For` только от Caddy

**Требования:** REQ-005.

**Критерии приёмки:** в `docker/compose.yaml` сеть `default` получает
фиксированную подсеть, Caddy — фиксированный `ipv4_address`; backend
запускается с `FORWARDED_ALLOW_IPS=<адрес Caddy>` (Uvicorn читает эту
переменную) или эквивалентным флагом в `docker/Dockerfile`. Через Caddy
`request.client.host` — адрес браузера; при прямом обращении из другого
контейнера с подставленным `X-Forwarded-For` — адрес соединения. Для
локального запуска без Docker поведение Uvicorn по умолчанию документируется.

**Файлы:** `docker/compose.yaml`, при необходимости `docker/Dockerfile`.

**Проверка:** ручная в изолированном Compose-проекте: временная
диагностическая проверка `request.client.host` (например, по журналу
отказа `429` после задачи 4 или временным `curl` к ручке с журналированием
IP в отладочном режиме, не коммитится) через Caddy и напрямую
(`docker compose exec frontend wget --header 'X-Forwarded-For: 1.2.3.4' …
http://backend:8000/...`). Результат записывается в verification.

## Задача 2. Доменный ограничитель и конфигурация

**Требования:** REQ-001, REQ-002, REQ-004.

**Критерии приёмки:**
- Модель `RateLimitConfig` (frozen, `extra="forbid"`): `login_failures` = 5,
  `login_failure_window_seconds` = 900, `login_per_ip` = 30,
  `login_per_ip_window_seconds` = 60, `register_per_ip` = 10,
  `register_per_ip_window_seconds` = 3600; переменные
  `AUTH_LOGIN_MAX_FAILURES`, `AUTH_LOGIN_FAILURE_WINDOW_SECONDS`,
  `AUTH_LOGIN_MAX_PER_IP`, `AUTH_LOGIN_PER_IP_WINDOW_SECONDS`,
  `AUTH_REGISTER_MAX_PER_IP`, `AUTH_REGISTER_PER_IP_WINDOW_SECONDS` читает
  только `load_config`.
- Контракт `AttemptLimiter` (async): `hit(key, limit, window) -> retry_after |
  None` для счётчиков запросов, `blocked(key, limit) -> retry_after | None`,
  `record_failure(key, window)` и `reset(key)` для неудач. Ключи строятся
  сервисом (`login-fail:<lower(login)>:<ip>`, `login-ip:<ip>`,
  `register-ip:<ip>`); логин хешируется SHA-256 в ключе, чтобы не хранить его
  открыто.
- In-memory реализация с инжектируемыми часами в `auth/memory.py`.
- Класс-координатор (например, `LoginThrottle`) или методы `AuthService`,
  которые принимают IP: `AuthService.login(login, password, client_ip)` и
  `register(..., client_ip)` бросают `TooManyAttemptsError(retry_after)` до
  проверки пароля; неудача — `record_failure`, успех — `reset`.

**Файлы:** `backend/src/smeshariki_ai/auth/{config,models,stores,memory,service}.py`,
`backend/src/smeshariki_ai/config.py`,
`backend/tests/unit/auth/test_auth_service.py`,
`backend/tests/unit/auth/test_rate_limit.py` (новый),
`backend/tests/unit/test_backend_config.py`.

**Проверка:** `uv run --project backend --locked pytest backend/tests/unit`.

## Задача 3. Redis-адаптер и bootstrap

**Требования:** REQ-004.

**Критерии приёмки:** `RedisAttemptLimiter` в `smeshariki_ai.cache`:
префикс `auth:ratelimit:`, атомарные `INCR` + `EXPIRE NX` в pipeline
(`transaction=True`), `retry_after` из `TTL`; ошибки — `AuthUnavailableError`.
Bootstrap передаёт адаптер в `AuthService`; `create_admin` не затронут.

**Файлы:** `backend/src/smeshariki_ai/cache/{__init__,rate_limit}.py`,
`backend/src/smeshariki_ai/bootstrap.py`,
`backend/tests/integration/cache/test_redis_rate_limit.py` (новый),
`backend/tests/unit/test_bootstrap.py`.

**Проверка:** временный `redis:7-alpine` и
`TEST_REDIS_URL=redis://127.0.0.1:<port>/0 uv run --project backend --locked pytest backend/tests/integration/cache backend/tests/unit/test_bootstrap.py`.

## Задача 4. HTTP: `429` и `Retry-After`

**Требования:** REQ-001…REQ-004, REQ-009.

**Критерии приёмки:** `register` и `login` в `api/auth.py` передают
`request.client.host`; `TooManyAttemptsError` →
`429` `{"error":"too_many_attempts"}` и `Retry-After`; порядок
`403`→`415`→`429`→`422`: лимит по IP проверяется до разбора тела, а
`login-fail` — после валидации (нужен логин), но до проверки пароля; запрос с
невалидным телом расходует только лимит по IP. Событие
`auth.rate_limit.rejected` с `limit` (`login_failures`/`login_ip`/
`register_ip`) без логина и IP. Тесты на in-memory ограничителе: шестая
попытка с верным паролем — `429` и `verify` не вызван (spy hasher);
`503` при недоступном ограничителе.

**Файлы:** `backend/src/smeshariki_ai/api/auth.py`,
`backend/tests/integration/api/test_auth.py` или новый
`backend/tests/integration/api/test_rate_limit.py`.

**Проверка:** `uv run --project backend --locked pytest backend/tests/integration/api`.

## Задача 5. Ограничение параллельности argon2

**Требования:** REQ-006.

**Критерии приёмки:** `Argon2PasswordHasher(max_concurrency=4)` оборачивает
`hash` и `verify` в `asyncio.Semaphore`; создание `dummy_hash` в конструкторе
не меняется. Тест с подменённой функцией хеширования и счётчиком
одновременных вызовов.

**Файлы:** `backend/src/smeshariki_ai/auth/passwords.py`,
`backend/tests/unit/auth/test_passwords.py` (новый).

**Проверка:** `uv run --project backend --locked pytest backend/tests/unit/auth`.

## Задача 6. Frontend

**Требования:** REQ-007, REQ-008.

**Критерии приёмки:**
- `refreshSession(api, { locks = globalThis.navigator?.locks } = {})`: при
  наличии `locks.request` выполняет под блокировкой `"smeshariki-auth-refresh"`
  сначала `api.me()`, и только при `unauthorized` — `api.refresh()`; без
  `locks` — прежний вызов `refresh`. `checkSession` использует его.
- `AuthApi.register` и `login` переводят `429` в `too_many_attempts`;
  `/login/` показывает «Слишком много попыток. Попробуйте позже» по
  существующему механизму `ERROR_MESSAGES`, логин сохраняется, пароль
  очищается.

**Файлы:** `frontend/src/auth-session.js`, `frontend/src/auth-api.js`,
`frontend/src/login/*.js`, `frontend/tests/{auth-session,auth-api,login-ui}.test.js`.

**Проверка:** `npm --prefix frontend test`, `npm --prefix frontend run build`.

## Задача 7. Документация и итоговая проверка

**Требования:** REQ-010.

**Проверка:** ревью `docs/auth.md`, `docs/configuration.md`,
`docker/README.md`, `docker/.env.example`, `AGENTS.md`, `docs/README.md`;
`make test`; `make lint`; runtime в `make run`: шестая неверная попытка на
`/login/` показывает ошибку, через окно вход доступен; две вкладки после
удаления cookie `access_token` остаются в системе.
