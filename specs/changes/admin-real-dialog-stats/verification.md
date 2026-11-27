# Verification: настоящая статистика диалогов в панели администратора

Исторический оригинал: `git show 5af56b5:specs/changes/admin-real-dialog-stats/verification.md`.

## Результат

- У пустого отрезка столбик скрыт (`adm-chart-bar-empty`), подписи — в формате «24.09». Пример формата в спецификации (REQ-005) обновлён с «12 окт.» на «12.10». - Документация и комментарии больше не упоминают demo-данные (`docs/admin.md`, `docs/README.md`, `docs/auth.md`, `frontend/README.md`, `AGENTS.md`).
- Команды: `make test` — frontend: 181 passed; backend: 400 passed, 38 skipped (тесты PostgreSQL/Redis без `TEST_*_URL`)
- Команды: `TEST_DATABASE_URL=… pytest backend/tests/integration/db` на временном `postgres:17-alpine` — 35 passed
- Команды: `make lint` — `All checks passed!`
- Команды: `docker compose … up -d --build backend frontend` — контейнеры пересобраны; миграции не нужны
- Тесты, которые падали до реализации:**
- PostgreSQL — 2 теста;
- сервис — сбор тестов падал на импорте `ActivityPoint`; API-тест — новые поля;
- frontend — 7 тестов (разбор ответа и UI панели).
- Отклонения:**
- У `AdminStatsStore.user_stats` параметры `bucket` и `buckets` именованные со значениями по умолчанию, чтобы не переписывать существующие вызовы в тестах; сервис всегда передаёт их явно.
- `demo-data.js` и `tests/admin-data.test.js` удалены. Тест «missing demo data keeps the safe error state» удалён вместе с параметром `getData`.
- Три новые проверки UI сначала сравнивали весь текст карточки, куда входит значок; заменены на проверку значения карточки.
- При ручной проверке нашлись два визуальных недочёта:
- у нулевых отрезков рисовался «пенёк» `min-height: 12px`;
- на 390 px подписи «24 сент.» переносились на две строки.
