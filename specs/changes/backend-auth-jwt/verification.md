# Проверка: аутентификация в backend — JWT, refresh-токены и пользователи в PostgreSQL

Исторический оригинал: `git show 5af56b5:specs/changes/backend-auth-jwt/verification.md`.

## Результат

- Изменение успешно прошло verify 2026-10-16. В backend добавлены пакет `smeshariki_ai.auth`, HTTP-роутер аутентификации, адаптеры PostgreSQL и Redis, Alembic-миграция `0001`, подконфиги `auth`/`database`/`redis` и сервисы `postgres`, `redis`, `migrate` в Compose. Frontend не менялся.
- uv run --project backend --locked pytest backend/tests/integration/db     # 4 passed
- uv run --project backend --locked pytest backend/tests/integration/cache  # 3 passed
- Вместо `backend/alembic.ini` миграции запускаются командой `python -m smeshariki_ai.db.migrate`: так URL приходит из `load_config`, и правило «environment читает только `load_config`» сохраняется.
- `Makefile` запускает `pytest backend`: без аргумента pytest из корня не видел `backend/pyproject.toml`, и `asyncio_mode = "auto"` не применялся к async тестам.
- В `compose.yaml` добавлено явное имя проекта `smeshariki-ai`. Раньше имя выводилось из каталога `docker/` и совпадало с другим локальным проектом, у которого тоже есть сервис `postgres` и том `docker_postgres-data`.
- Интеграционные тесты PostgreSQL и Redis в `make test` пропускаются без `TEST_DATABASE_URL` и `TEST_REDIS_URL`; они выполнены вручную командами выше.
- Визуальная проверка `/login/` в браузере не выполнялась: frontend не менялся, совместимость контракта подтверждена реальным клиентом.
- Автоматический refresh во frontend, защита чата, создание администратора и rate limiting — вне изменения (см. «Границы» спецификации).
- После смены имени Compose-проекта ранее запущенные контейнеры старого проекта `docker` (`docker-backend-1`, `docker-frontend-1`, `docker-caddy-1`) нужно остановить вручную, иначе они продолжат занимать порт `8080`.
