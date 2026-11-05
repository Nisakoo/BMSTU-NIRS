# План: настоящая статистика диалогов в панели администратора

Спецификация: [spec.md](./spec.md).

## Порядок

Рискованная часть — SQL-подсчёт по отрезкам окна и исключение пустых
диалогов — идёт первой и проверяется на временной PostgreSQL. Затем сервис и
API, frontend, удаление демо-данных, документация, ручная проверка.

## Решения

- `StatsPeriod` получает число отрезков: 7 → 7, 30 → 10, 90 → 9; длина
  отрезка `timedelta(days=period.days / buckets)` (1, 3 и 10 дней).
- Контракт `AdminStatsStore.user_stats(since, limit, *, bucket, buckets)`:
  хранилище считает отрезок как `floor((created_at − since) / bucket)`,
  ограниченный `[0, buckets − 1]`, и возвращает в снимке
  `dialogs: int`, `messages: int`, `activity: tuple[int, ...]` (длина
  `buckets`), а у `RecentUser` — `dialogs: int`. Новые поля снимка имеют
  значения по умолчанию, чтобы старые фейки тестов не ломались без нужды.
- `AdminStatsService` превращает счётчики в
  `ActivityPoint(start: datetime, dialogs: int)`, где
  `start = since + i * bucket`.
- SQL: история — `dialogs` с `EXISTS` сообщения; `messages` — все сообщения
  с `created_at >= since`; отрезки — `GROUP BY` по выражению отрезка; число
  историй пользователя — подзапрос с `GROUP BY dialogs.user_id`.
- API: `dialogs`, `messages`, `activity: [{"start", "dialogs"}]`,
  `recent_users[].dialogs`.
- Frontend: `AdminApi` разбирает и проверяет новые поля (сумма `activity`
  равна `dialogs`); `mountDashboard` больше не принимает `getData`;
  карточки берут все четыре значения из статистики; подпись столбца —
  `DATE_FORMATTER` по `start`; демо-модуль, его тест, метки и подсказка
  удаляются.

## Задача 1. PostgreSQL-подсчёт

**Требования:** REQ-001, REQ-002, REQ-003.

**Критерии приёмки:** пустые диалоги не считаются; истории и сообщения вне
окна не считаются; отрезки и их сумма; `dialogs` у пользователей.

**Файлы:** `admin/models.py`, `admin/stores.py`, `db/admin_stats.py`,
`tests/integration/db/test_postgres_admin_stats.py`.

**Проверка:** на временном `postgres:17-alpine`
`TEST_DATABASE_URL=… uv run --project backend --locked pytest backend/tests/integration/db/test_postgres_admin_stats.py`.

## Задача 2. Сервис и API

**Требования:** REQ-001–REQ-003.

**Критерии приёмки:** отрезки 7/30/90 передаются в хранилище, `start`
отрезков; новые поля в ответе; права и ошибки прежние.

**Файлы:** `admin/{models,service,__init__}.py`, `api/admin.py`,
`tests/unit/admin/test_admin_stats_service.py`,
`tests/integration/api/test_admin_stats.py`.

**Проверка:** `uv run --project backend --locked pytest backend/tests/unit/admin backend/tests/integration/api/test_admin_stats.py`.

## Задача 3. Frontend без демо-данных

**Требования:** REQ-004–REQ-007.

**Критерии приёмки:** карточки, график, пустой период, колонка «Диалоги»;
нет «демо-данные»; смена периода; ошибки прежние.

**Файлы:** `frontend/src/admin/{admin-api.js,admin.js,index.html,admin.css}`,
удаление `frontend/src/admin/demo-data.js` и `frontend/tests/admin-data.test.js`,
`frontend/tests/{admin-api,admin-ui}.test.js`.

**Проверка:** `cd frontend && npm test`.

## Задача 4. Документация

**Файлы:** `docs/admin.md`, `docs/README.md`, `frontend/README.md`,
`AGENTS.md`.

**Проверка:** ревью; `make test`, `make lint`.

## Задача 5. Ручная проверка

`make run`: панель на настоящих данных за 7/30/90 дней, сверка с SQL,
телефон 390 px.
