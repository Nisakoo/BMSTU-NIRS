# Verification: конфигурация Nginx для frontend

Спецификация: [spec.md](./spec.md), план: [plan.md](./plan.md).

## Команды

| Команда | Результат |
| --- | --- |
| `APP_PORT=18080 docker compose -p smeshariki-verify -f docker/compose.yaml up -d --build --wait` | все сервисы healthy, после проверки `down -v` |
| `nginx -t` в образе frontend (реализатор) | `syntax is ok`, `test is successful` |
| `make test` (регрессия) | frontend 103/103 pass; backend `328 passed, 16 skipped` |

## Требования

| Требование | Проверка через Caddy на порту 18080 | Итог |
| --- | --- | --- |
| REQ-001 | `/login` → `301`, `Location: /login/`; `/admin` → `301` на `/admin/`; `curl -L` → `200 http://127.0.0.1:18080/login/` и `/admin/` | ✅ |
| REQ-002 | `/`, `/login/`, `/admin/` → `Cache-Control: no-cache` | ✅ |
| REQ-003 | `/assets/main-*.js` → `public, max-age=31536000, immutable`; `/assets/missing.js` → `404` без `Cache-Control` | ✅ |
| REQ-004 | `/nope` → `404`; `/api/v1/users/me` → `401` (маршрутизация Caddy не изменилась) | ✅ |
| REQ-005 | Ревью: `docker/nginx.conf` копируется в `/etc/nginx/conf.d/default.conf`; frontend healthy | ✅ |
| REQ-006 | Ревью `docker/README.md`, `frontend/README.md`, `AGENTS.md`, `docs/README.md` | ✅ |

## Известные ограничения

- `add_header` без `always`: заголовки кэша ставятся только на успешные ответы
  и редиректы, поэтому `404` не кэшируется.
- Проверка в реальном браузере выполнялась только через `curl`.
