# Verification: ограничение частоты входа и одновременный refresh

Спецификация: [spec.md](./spec.md), план: [plan.md](./plan.md).

## Команды

| Команда | Результат |
| --- | --- |
| `make test` | frontend 103/103 pass; backend `328 passed, 16 skipped` (PostgreSQL без `TEST_DATABASE_URL`, Redis без `TEST_REDIS_URL`) |
| `make lint` | `All checks passed!`, `93 files already formatted` |
| `TEST_REDIS_URL=… pytest backend/tests/integration/cache` (временный `redis:7-alpine`) | `9 passed` |
| `APP_PORT=18080 docker compose -p smeshariki-verify -f docker/compose.yaml up -d --build --wait` | стек поднят, после проверки `down -v` |

## Требования

| Требование | Проверка | Итог |
| --- | --- | --- |
| REQ-001 | Runtime через Caddy: 5 неверных паролей → `401`×5, шестая попытка с верным паролем и логином в другом регистре → `429`, `Retry-After: 900`; другой логин с того же IP входит (`200`); unit `test_rate_limit.py` — окна, сброс при успехе | ✅ |
| REQ-002 | Runtime: 32 запроса входа с невалидным телом за минуту → 30×`422`, затем `429`; integration `test_auth_rate_limit.py` для регистрации | ✅ |
| REQ-003 | Runtime: `403` (`Sec-Fetch-Site`), `415` (`text/plain`), `422` (невалидное тело); integration-тесты порядка с `429` | ✅ |
| REQ-004 | Runtime: остановленный Redis → `503 {"error":"unavailable"}`; Redis-тест `test_redis_rate_limit.py` (TTL, `EXPIRE NX`); unit-тест загрузки конфигурации | ✅ |
| REQ-005 | Runtime: `X-Forwarded-For: 9.9.9.9` через Caddy не снимает блокировку (`429`); реализатор временным логом подтвердил, что при прямом `wget` из контейнера `frontend` с подставленным XFF backend видит адрес соединения (`172.31.250.4`), лог удалён | ✅ |
| REQ-006 | Unit `test_passwords.py`: не более 4 одновременных операций | ✅ |
| REQ-007 | Node-тесты с fake `navigator.locks`: refresh под блокировкой, повтор `/users/me`, прежнее поведение без Web Locks | ✅ |
| REQ-008 | Node-тесты `auth-api`, `login-ui`: `429` → `too_many_attempts`, текст на `/login/` | ✅ |
| REQ-009 | Runtime: в логе `event="auth.rate_limit.rejected" limit="login_failures" outcome="rejected"` без логина, пароля и IP | ✅ |
| REQ-010 | Ревью `docs/auth.md`, `docs/configuration.md`, `docker/README.md`, `docker/.env.example`, `AGENTS.md`, `docs/README.md` | ✅ |

## Scope и отклонения

- `compose.yaml`: фиксированная подсеть `172.31.250.0/24`, динамические адреса
  ограничены `ip_range` нижней половиной, Caddy — `172.31.250.250`,
  `FORWARDED_ALLOW_IPS` у backend; проброшены шесть новых `AUTH_*`.
- Лимит регистрации по IP вызывается отдельным `AuthService.limit_register_ip`
  до разбора тела.
- `frontend/tests/no-web-locks.js` изолирует прежние Node-тесты от
  `navigator.locks` в новых версиях Node.

## Известные ограничения

- Проверка блокировки и запись неудачи не атомарны: одновременный залп
  неверных попыток одной пары может превысить 5, но остаётся ограничен лимитом
  входов по IP (30 в минуту).
- Фиксированная подсеть не позволяет одновременно запускать два Compose-проекта
  из этого файла; существующую сеть `smeshariki-ai_default` со старой
  подсетью нужно пересоздать (`docker compose -f docker/compose.yaml down`).
- На Docker Desktop for Mac backend видит через Caddy адрес шлюза Docker
  (все клиенты хоста — один IP); на Linux — реальный адрес клиента.
- Web Locks в реальном браузере с двумя вкладками вручную не проверялись.
