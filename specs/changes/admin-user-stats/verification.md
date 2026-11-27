# Verification: реальная статистика пользователей в панели администратора

Исторический оригинал: `git show 5af56b5:specs/changes/admin-user-stats/verification.md`.

## Результат

- 11 пропусков в `make test` — интеграционные тесты PostgreSQL и Redis без `TEST_DATABASE_URL`/`TEST_REDIS_URL`; тесты PostgreSQL отдельно запущены и прошли на временной базе, контейнер после проверки удалён.
- Итоговые команды: `make lint` — `All checks passed!`, 86 файлов отформатированы
- Итоговые команды: `make test` — frontend: 98 passed, 0 failed; backend: 249 passed, 11 skipped
- Итоговые команды: `TEST_DATABASE_URL=… pytest backend/tests/integration/db` на временном `postgres:17-alpine` — 8 passed (4 новых теста статистики и 4 существующих теста хранилищ)
- Итоговые команды: `npm --prefix frontend run build` — успешная сборка
- `active_users` считает созданные refresh-сессии: вход и продление сессии. Пользователь, открывший сайт с действующим access-токеном без продления, не учитывается до следующего `refresh`.
- Показатели агента остаются демонстрационными до отдельного изменения, которое сохранит диалоги и результаты запусков агента.
- Ручная проверка панели в браузере против `make run` пользователем не выполнялась.
