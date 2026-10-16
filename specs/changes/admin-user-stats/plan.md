# План: реальная статистика пользователей в панели администратора

Спецификация: [spec.md](./spec.md).

## Порядок

Сначала доменная часть и HTTP-ручка на фиктивном хранилище — это фиксирует
контракт. Затем адаптер PostgreSQL с проверкой на временной базе (рискованная
часть — SQL подсчёта и сортировки). После этого frontend: клиент, панель,
метки. Документация — последней.

## Задача 1. Сервис статистики и защищённая ручка

**Требования:** REQ-001…REQ-005.

**Критерии приёмки:** `AdminStatsService.user_stats(period)` вычисляет окно
по инжектируемым часам и делегирует хранилищу; статусы `new`/`active`/
`inactive` по REQ-002; `GET /api/v1/admin/stats` отвечает `401`, `403`
(`{"error":"forbidden"}`), `503` до валидации `period`, `422` администратору с
неверным периодом, `200` с контрактом REQ-001; без хранилища — `503`.

**Файлы:** `backend/src/smeshariki_ai/admin/{__init__,models,stores,service}.py`,
`backend/src/smeshariki_ai/api/admin.py`, `backend/src/smeshariki_ai/api/auth.py`
(зависимость `current_admin`), `backend/src/smeshariki_ai/api/app.py`,
`backend/tests/unit/admin/test_admin_stats_service.py`,
`backend/tests/integration/api/test_admin_stats.py`.

**Проверка:** `uv run --project backend --locked pytest backend/tests/unit/admin backend/tests/integration/api`.

## Задача 2. Адаптер PostgreSQL и bootstrap

**Требования:** REQ-002, REQ-005.

**Критерии приёмки:** `PostgresAdminStatsStore` считает `users_total`,
`new_users`, `active_users` и возвращает до 5 `recent_users` с
`last_active_at` по REQ-002; ошибки БД превращаются в недоступность
(`503`); bootstrap передаёт хранилище в `create_app`.

**Файлы:** `backend/src/smeshariki_ai/db/stores.py` (или
`db/admin_stats.py`), `backend/src/smeshariki_ai/db/__init__.py`,
`backend/src/smeshariki_ai/bootstrap.py`,
`backend/tests/integration/db/test_postgres_admin_stats.py`,
`backend/tests/unit/test_bootstrap.py`.

**Проверка:** временный контейнер `postgres:17-alpine` и
`TEST_DATABASE_URL=… uv run --project backend --locked pytest backend/tests/integration/db`.

## Задача 3. Frontend

**Требования:** REQ-006…REQ-011.

**Критерии приёмки:** `AdminApi.stats(period)` с кодами `unauthorized`,
`forbidden`, `unavailable`, `invalid_response`; панель показывает реальные
карточки пользователей, число новых, список с логином, ролью, временем
активности и статусом, «—» в диалогах; блоки агента с меткой «демо-данные»;
общие demo-надписи удалены; переключение периода с блокировкой кнопок;
переходы при `401`/`403`; ошибка без данных; только `textContent`.

**Файлы:** `frontend/src/admin/admin-api.js`, `frontend/src/admin/admin.js`,
`frontend/src/admin/index.html`, `frontend/src/admin/admin.css`,
`frontend/src/admin/demo-data.js`, `frontend/tests/admin-api.test.js`,
`frontend/tests/admin-ui.test.js`, `frontend/tests/admin-data.test.js`.

**Проверка:** `npm --prefix frontend test`, `npm --prefix frontend run build`.

## Задача 4. Документация и итоговая проверка

**Требования:** REQ-012.

**Проверка:** ревью `docs/admin.md`, `docs/README.md`, `frontend/README.md`,
`AGENTS.md`; `make test`, `make lint`; runtime в изолированном Compose-проекте.
