# План: CSRF, секрет подписи и отзыв сессии

Спецификация: [spec.md](./spec.md).

## Порядок

Сначала токены и отзыв семейства — это меняет внутренний контракт
`TokenBlacklist`/`AccessClaims`, от которого зависит перепроверка SSE. Затем
независимые HTTP-проверки (`Sec-Fetch-Site`, media type), секрет, SSE.
Документация — последней. Существующие тесты, которые строят токены или
вызывают ручки без `Content-Type`, обновляются в той задаче, где ломаются.

## Задача 1. Claim `fid` и отзыв семейства

**Требования:** REQ-007…REQ-010.

**Критерии приёмки:**
- `AccessClaims` получает `family_id`; `TokenCodec.encode_access` принимает
  его и пишет claim `fid`; `fid` входит в `_REQUIRED_CLAIMS`; токен без `fid`
  или с некорректным UUID даёт `UnauthorizedError`.
- `AuthService._result` передаёт `session.family_id`.
- Контракт `TokenBlacklist` расширяется методами
  `revoke_family(family_id: UUID, until: datetime)` и
  `family_revoked(family_id: UUID) -> bool` (имена можно уточнить, смысл —
  нет). `InMemoryTokenBlacklist` и `RedisTokenBlacklist` реализуют их;
  Redis — ключ `auth:revoked-family:<uuid>` с TTL до `until`, ошибки — в
  `AuthUnavailableError`.
- `logout`: для действительного access-токена — blacklist `jti`,
  `sessions.revoke_family(claims.family_id)` и `blacklist.revoke_family(
  claims.family_id, now + access_ttl)`; для найденного refresh-токена —
  то же по `session.family_id`. Отзыв одной сессии (`sessions.revoke`) больше
  не используется в `logout`.
- `_reject_reuse` дополнительно вызывает `blacklist.revoke_family`.
- `authenticate` после декодирования проверяет `jti` и `fid`; оба запроса к
  Redis — после проверки подписи, `iss` и `exp`.

**Файлы:** `backend/src/smeshariki_ai/auth/{models,tokens,service,stores,memory}.py`,
`backend/src/smeshariki_ai/cache/blacklist.py`,
`backend/tests/unit/auth/{test_tokens,test_auth_service}.py`,
`backend/tests/integration/cache/test_redis_blacklist.py`.

**Проверка:** `uv run --project backend --locked pytest backend/tests/unit/auth backend/tests/integration/api/test_auth.py`;
Redis-тесты — временный `redis:7-alpine` и
`TEST_REDIS_URL=redis://127.0.0.1:<port>/0 uv run --project backend --locked pytest backend/tests/integration/cache`.

## Задача 2. Проверка `Sec-Fetch-Site`

**Требования:** REQ-003, REQ-004 (часть `403`), REQ-013.

**Критерии приёмки:** middleware в `api/` (по образцу `RequestLogMiddleware`
в `observability.py`) для путей `/api` и `/api/*` и методов
`POST`/`PUT`/`PATCH`/`DELETE` отвечает `403` `{"error":"forbidden_origin"}`
при `Sec-Fetch-Site` ∈ {`cross-site`, `same-site`} (без учёта регистра) и не
вызывает обработчик; иначе пропускает. Подключается в `create_app` так, чтобы
отказ получал `X-Request-ID` и попадал в журнал HTTP-запроса; отдельное
событие `http.request.forbidden_origin` без заголовков запроса.

**Файлы:** `backend/src/smeshariki_ai/api/security.py` (новый),
`backend/src/smeshariki_ai/api/app.py`,
`backend/tests/integration/api/test_auth.py` или новый
`backend/tests/integration/api/test_security.py`.

**Проверка:** `uv run --project backend --locked pytest backend/tests/integration/api`.

## Задача 3. Media type у регистрации, входа и `messages`

**Требования:** REQ-001, REQ-002, REQ-004, REQ-013.

**Критерии приёмки:**
- Общая функция проверки `Content-Type` (media type `application/json`,
  параметры допустимы, регистр не важен; отсутствие заголовка — отказ).
- `_read_credentials` до чтения тела отвечает `415`
  `{"error":"unsupported_media_type"}`.
- `_read_submit_request` до разбора тела отвечает `415` через
  `HTTPException(detail="Unsupported media type.")`; `401` по-прежнему
  раньше, так как зависимость роутера выполняется до обработчика.
- Событие журнала `http.request.unsupported_media_type` без значения
  заголовка.
- `agent_test.html` и frontend уже отправляют `application/json` — проверить
  ревью, не менять без необходимости.

**Файлы:** `backend/src/smeshariki_ai/api/{auth,app,security}.py`,
`backend/tests/integration/api/{test_auth,test_dialogs}.py`.

**Проверка:** `uv run --project backend --locked pytest backend/tests/integration/api`.

## Задача 4. Запрет заглушки секрета

**Требования:** REQ-005, REQ-006.

**Критерии приёмки:** `AuthConfig.require_long_secret` также отклоняет
значения с префиксом `replace-with-`; сообщение ошибки не содержит значения
(`hide_input_in_errors` уже включён — проверить тестом). В
`docker/.env.example` строка `AUTH_JWT_SECRET=` пустая, комментарий с
`openssl rand -base64 48` сохраняется; `docker compose -f docker/compose.yaml
config` с пустым значением падает с `Set AUTH_JWT_SECRET in docker/.env`.

**Файлы:** `backend/src/smeshariki_ai/auth/config.py`, `docker/.env.example`,
`backend/tests/unit/test_backend_config.py`.

**Проверка:** `uv run --project backend --locked pytest backend/tests/unit/test_backend_config.py`;
ручной `docker compose --env-file <временный файл> -f docker/compose.yaml config`.

## Задача 5. Перепроверка сессии в SSE

**Требования:** REQ-011, REQ-012, REQ-013.

**Критерии приёмки:**
- `TokenCodec.decode_access(..., verify_expiry: bool = True)`; новый
  `AuthService.verify_session(access_token) -> User`: подпись, `iss`, отзыв
  `jti`/`fid`, существование пользователя, без проверки `exp`.
- `stream_dialog_events` получает access-токен из cookie (`Cookie` параметр)
  и в ветке heartbeat (`TimeoutError`) вызывает `verify_session`; при
  `UnauthorizedError` или `AuthUnavailableError` генератор завершается (не
  отправляя keep-alive), `finally` отписывает подписчика. Agent loop не
  отменяется.
- Событие `dialog.subscription.revoked` с `dialog_id` и исходом
  (`revoked`/`unavailable`).
- Тест: короткий `heartbeat_seconds`, вход, подписка, `logout` тем же
  токеном → поток завершается; токен с истёкшим `exp` (управляемые часы) не
  закрывает поток.

**Файлы:** `backend/src/smeshariki_ai/auth/{tokens,service}.py`,
`backend/src/smeshariki_ai/api/app.py`,
`backend/tests/unit/auth/test_auth_service.py`,
`backend/tests/integration/api/test_sse.py`,
`backend/tests/integration/api/api_auth_support.py` (если нужен fake с
`verify_session`).

**Проверка:** `uv run --project backend --locked pytest backend/tests/unit/auth backend/tests/integration/api`.

## Задача 6. Документация и итоговая проверка

**Требования:** REQ-014, REQ-015.

**Критерии приёмки:** обновлены `docs/auth.md` (таблица токенов с `fid`,
blacklist семейств, logout, проверки `415`/`403`, раздел о защищённых ручках
и SSE), `docs/dialogs.md`, `docs/configuration.md`, `docker/README.md`,
`AGENTS.md`, `docs/README.md`; ссылки на артефакты `auth-hardening`.

**Проверка:** ревью документации; `make test`; `make lint`; runtime в
`make run`: вход, чат, выход во второй вкладке закрывает поток, `curl` с
`Content-Type: text/plain` даёт `415`, с `Sec-Fetch-Site: cross-site` — `403`.
