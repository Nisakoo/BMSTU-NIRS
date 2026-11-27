# Verification: CSRF, секрет подписи и отзыв сессии

Исторический оригинал: `git show 5af56b5:specs/changes/auth-hardening/verification.md`.

## Результат

- Команды: `make test` — frontend 98/98 pass; backend `296 passed, 13 skipped` (PostgreSQL-тесты без `TEST_DATABASE_URL`)
- Команды: `make lint` — `All checks passed!`, `88 files already formatted`
- Команды: `TEST_REDIS_URL=… pytest backend/tests/integration/cache` (временный `redis:7-alpine`) — `5 passed`
- Команды: `APP_PORT=18080 docker compose -p smeshariki-verify -f docker/compose.yaml up -d --build --wait` — стек поднят, после проверки `down -v`
- `Sec-Fetch-Site` в runtime эмулирован `curl`; реальная кросс-сайтовая форма в браузере и переход второй вкладки на `/login/` вручную в браузере не проверялись (frontend-логика перехода при ошибке SSE покрыта существующими Node-тестами).
- Интеграционные тесты PostgreSQL пропущены; `revoke_family` для PostgreSQL не менялся.
- Задачи 1–3 и 5 реализованы без строгого RED-шага (тесты добавлены сразу после кода), что не влияет на итоговое покрытие требований.
