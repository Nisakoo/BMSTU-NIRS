# Verification: CSRF, секрет подписи и отзыв сессии

Спецификация: [spec.md](./spec.md), план: [plan.md](./plan.md).

## Команды

| Команда | Результат |
| --- | --- |
| `make test` | frontend 98/98 pass; backend `296 passed, 13 skipped` (PostgreSQL-тесты без `TEST_DATABASE_URL`) |
| `make lint` | `All checks passed!`, `88 files already formatted` |
| `TEST_REDIS_URL=… pytest backend/tests/integration/cache` (временный `redis:7-alpine`) | `5 passed` |
| `APP_PORT=18080 docker compose -p smeshariki-verify -f docker/compose.yaml up -d --build --wait` | стек поднят, после проверки `down -v` |

## Требования

| Требование | Проверка | Итог |
| --- | --- | --- |
| REQ-001 | Runtime через Caddy: регистрация с `text/plain` → `415`, вход с `text/plain` и без `Content-Type` → `415`, с `application/json` → `201`/`200`; integration `test_security.py` | ✅ |
| REQ-002 | Runtime: `messages` с `text/plain` и cookie → `415`, без cookie → `401`; integration-тесты | ✅ |
| REQ-003 | Runtime: вход с `Sec-Fetch-Site: cross-site` → `403`, с `same-origin` → `200`, SSE `GET` с `cross-site` → `200`; integration-тесты на `same-site`, `none`, отсутствие заголовка | ✅ |
| REQ-004 | Integration-тесты порядка `403`→`415`→`422` | ✅ |
| REQ-005 | Unit `test_backend_config.py`; runtime: backend-контейнер с `replace-with-…` падает `JWT secret must not be a placeholder value.` без значения в ошибке | ✅ |
| REQ-006 | Ревью `docker/.env.example` (`AUTH_JWT_SECRET=`); `docker compose config` с пустым секретом → `Set AUTH_JWT_SECRET in docker/.env` | ✅ |
| REQ-007 | Unit `test_tokens.py`: `fid` выпускается, токен без `fid`/с некорректным UUID отклоняется | ✅ |
| REQ-008, REQ-009 | Unit `test_auth_service.py`: logout и reuse отзывают семейство в сессиях и blacklist; Redis-тест ключа `auth:revoked-family:` с TTL; runtime: после logout копия старой cookie на `/users/me` → `401` | ✅ |
| REQ-010 | Unit: отклонение отозванного `fid`; порядок проверок по коду `AuthService._resolve` после `decode_access` | ✅ |
| REQ-011, REQ-012 | Integration `test_sse.py` (закрытие после logout, `exp` не закрывает); runtime: поток с копией cookie завершился через 13 с после logout при heartbeat 15 с | ✅ |
| REQ-013 | Ревью событий `http.request.forbidden_origin`, `http.request.unsupported_media_type`, `dialog.subscription.revoked` — без заголовков, токенов и текста | ✅ |
| REQ-014, REQ-015 | Ревью `docs/auth.md`, `docs/dialogs.md`, `docs/configuration.md`, `docker/README.md`, `AGENTS.md`, `docs/README.md` | ✅ |

## Scope

Изменения ограничены планом; тесты не отключены. Владение диалогами и rate
limiting не затронуты.

## Известные ограничения

- `Sec-Fetch-Site` в runtime эмулирован `curl`; реальная кросс-сайтовая форма
  в браузере и переход второй вкладки на `/login/` вручную в браузере не
  проверялись (frontend-логика перехода при ошибке SSE покрыта существующими
  Node-тестами).
- Интеграционные тесты PostgreSQL пропущены; `revoke_family` для PostgreSQL не
  менялся.
- Задачи 1–3 и 5 реализованы без строгого RED-шага (тесты добавлены сразу
  после кода), что не влияет на итоговое покрытие требований.
