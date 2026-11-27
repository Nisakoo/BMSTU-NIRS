# Verification: владение диалогами

Исторический оригинал: `git show 5af56b5:specs/changes/dialog-ownership/verification.md`.

## Результат

- Команды: `make test` — frontend 98/98 pass; backend `302 passed, 13 skipped` (PostgreSQL/Redis без `TEST_*_URL`)
- Команды: `make lint` — `All checks passed!`, `88 files already formatted`
- Команды: `APP_PORT=18080 docker compose -p smeshariki-verify -f docker/compose.yaml up -d --build --wait` — стек поднят, после проверки `down -v`
- Владелец хранится in-memory вместе с историей и теряется при рестарте, как и сами диалоги.
