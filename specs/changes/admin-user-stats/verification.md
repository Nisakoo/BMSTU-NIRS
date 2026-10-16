# Verification: реальная статистика пользователей в панели администратора

Спецификация: [spec.md](./spec.md), план: [plan.md](./plan.md).
Дата проверки: 2026-10-16, ветка `feat/auth-guard`.

## Итоговые команды

| Команда | Результат |
| --- | --- |
| `make lint` | `All checks passed!`, 86 файлов отформатированы |
| `make test` | frontend: 98 passed, 0 failed; backend: 249 passed, 11 skipped |
| `TEST_DATABASE_URL=… pytest backend/tests/integration/db` на временном `postgres:17-alpine` | 8 passed (4 новых теста статистики и 4 существующих теста хранилищ) |
| `npm --prefix frontend run build` | успешная сборка |

11 пропусков в `make test` — интеграционные тесты PostgreSQL и Redis без
`TEST_DATABASE_URL`/`TEST_REDIS_URL`; тесты PostgreSQL отдельно запущены и
прошли на временной базе, контейнер после проверки удалён.

## Требования

| Требование | Проверка | Результат |
| --- | --- | --- |
| REQ-001 | `test_admin_stats.py::test_admin_receives_user_statistics` (точный JSON); runtime-ответ | Выполнено |
| REQ-002 | `test_admin_stats_service.py` (окно 7/30/90, статусы); `test_postgres_admin_stats.py` (счётчики, distinct-активность, порядок и лимит `recent_users`, `last_active_at`) | Выполнено |
| REQ-003 | `test_guest_is_rejected_before_validation`, `test_regular_user_is_forbidden`, `test_admin_with_invalid_period_gets_422`, `test_unavailable_storage_returns_503`, `test_missing_stats_service_returns_503`; runtime: `401`, `403`, `422`, `503` при остановленном PostgreSQL | Выполнено |
| REQ-004 | Ревью `_stats_body`; `test_logs_do_not_contain_returned_logins`; runtime: логины отсутствуют в журнале backend | Выполнено |
| REQ-005 | Ревью: `admin` не импортирует FastAPI и SQLAlchemy, SQL в `db/admin_stats.py` | Выполнено |
| REQ-006 | `admin-ui.test.js`: `dashboard shows backend user figures…`, `period buttons reload statistics and are locked while loading` | Выполнено |
| REQ-007 | `admin-ui.test.js`: карточки, «Новых пользователей», `recent users show login, role, activity time, status and no dialog count`, `an empty user list…`, `activity time falls back to a date…` | Выполнено |
| REQ-008 | `admin-ui.test.js`: `only agent figures carry the demo label`; метки в разметке панелей активности и качества; скриншоты | Выполнено |
| REQ-009 | Ревью `admin/index.html` и `admin.css`: общие demo-надписи и их стили удалены; `admin-data.test.js` — demo-набор больше не содержит пользователей | Выполнено |
| REQ-010 | `admin-ui.test.js`: `a failed statistics request…`, `lost session or role…`, `the admin page redirects when statistics reject…` | Выполнено |
| REQ-011 | `admin-ui.test.js`: логин `<b>Pin</b>` выводится как текст; fake-элементы запрещают `innerHTML` | Выполнено |
| REQ-012 | Ревью `docs/admin.md` (новая), `docs/README.md`, `docs/auth.md`, `frontend/README.md`, `AGENTS.md` | Выполнено |

## Runtime-проверка

Изолированный Compose-проект `smeshariki-verify` (порт `18080`, отдельные
тома, удалён `down -v`): регистрация `krosh`, `nyusha`, `yozhik`, вход двух из
них, создание `sovunya` через `python -m smeshariki_ai.create_admin`.
`GET /api/v1/admin/stats?period=7` администратором вернул `users_total=4`,
`active_users=3`, `new_users=4` и четырёх пользователей по последней
активности, `yozhik` с `last_active_at: null`. Гость — `401`, `krosh` — `403`,
`period=5` — `422`, остановленный PostgreSQL — `503`.

Внешний вид проверен скриншотами headless Chrome (1280px и 375px) на Vite dev
server с временным mock-backend: карточки пользователей без меток, метки
«демо-данные» на карточках диалогов и сообщений и на панелях активности и
качества, пояснение под ними, список пользователей с «—» в колонке диалогов.
По скриншоту исправлен отступ пояснения.

## Известные ограничения

- `active_users` считает созданные refresh-сессии: вход и продление сессии.
  Пользователь, открывший сайт с действующим access-токеном без продления,
  не учитывается до следующего `refresh`.
- Показатели агента остаются демонстрационными до отдельного изменения,
  которое сохранит диалоги и результаты запусков агента.
- Ручная проверка панели в браузере против `make run` пользователем не
  выполнялась.
