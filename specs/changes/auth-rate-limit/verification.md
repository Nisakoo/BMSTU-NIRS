# Verification: ограничение частоты входа и одновременный refresh

Исторический оригинал: `git show 5af56b5:specs/changes/auth-rate-limit/verification.md`.

## Результат

- Команды: `make test` — frontend 103/103 pass; backend `328 passed, 16 skipped` (PostgreSQL без `TEST_DATABASE_URL`, Redis без `TEST_REDIS_URL`)
- Команды: `make lint` — `All checks passed!`, `93 files already formatted`
- Команды: `TEST_REDIS_URL=… pytest backend/tests/integration/cache` (временный `redis:7-alpine`) — `9 passed`
- Команды: `APP_PORT=18080 docker compose -p smeshariki-verify -f docker/compose.yaml up -d --build --wait` — стек поднят, после проверки `down -v`
- `compose.yaml`: фиксированная подсеть `172.31.250.0/24`, динамические адреса ограничены `ip_range` нижней половиной, Caddy — `172.31.250.250`, `FORWARDED_ALLOW_IPS` у backend; проброшены шесть новых `AUTH_*`.
- Лимит регистрации по IP вызывается отдельным `AuthService.limit_register_ip` до разбора тела.
- `frontend/tests/no-web-locks.js` изолирует прежние Node-тесты от `navigator.locks` в новых версиях Node.
- Проверка блокировки и запись неудачи не атомарны: одновременный залп неверных попыток одной пары может превысить 5, но остаётся ограничен лимитом входов по IP (30 в минуту).
- Фиксированная подсеть не позволяет одновременно запускать два Compose-проекта из этого файла; существующую сеть `smeshariki-ai_default` со старой подсетью нужно пересоздать (`docker compose -f docker/compose.yaml down`).
- На Docker Desktop for Mac backend видит через Caddy адрес шлюза Docker (все клиенты хоста — один IP); на Linux — реальный адрес клиента.
- Web Locks в реальном браузере с двумя вкладками вручную не проверялись.
