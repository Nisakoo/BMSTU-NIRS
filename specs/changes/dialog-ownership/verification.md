# Verification: владение диалогами

Спецификация: [spec.md](./spec.md), план: [plan.md](./plan.md).

## Команды

| Команда | Результат |
| --- | --- |
| `make test` | frontend 98/98 pass; backend `302 passed, 13 skipped` (PostgreSQL/Redis без `TEST_*_URL`) |
| `make lint` | `All checks passed!`, `88 files already formatted` |
| `APP_PORT=18080 docker compose -p smeshariki-verify -f docker/compose.yaml up -d --build --wait` | стек поднят, после проверки `down -v` |

## Требования

| Требование | Проверка | Итог |
| --- | --- | --- |
| REQ-001 | Unit `test_history.py` (владелец сохраняется); integration `test_dialogs.py` | ✅ |
| REQ-002 | Runtime: пользователь B на диалог A — `messages` `404`, `events` `404`, тело `{"detail":"Dialog not found."}` совпадает с телом для случайного UUID; integration: то же для администратора, агент не вызван, история пуста | ✅ |
| REQ-003 | Runtime: владелец получает `ready` в SSE; существующие тесты диалогов и SSE проходят | ✅ |
| REQ-004 | Ревью: проверка в `AgentService._ensure_owner`, HTTP-слой передаёт только `user.id` | ✅ |
| REQ-005 | Runtime: в логах backend 3 события `dialog.access.denied`; integration-тест — без текста запроса | ✅ |
| REQ-006 | Ревью `docs/dialogs.md`, `docs/auth.md`, `docs/README.md`, `AGENTS.md` | ✅ |

## Scope

Изменения ограничены планом; тесты не отключены. Схема БД не менялась.
Дополнительно обновлён `test_security.py` под новую сигнатуру сервиса.

## Известные ограничения

- Владелец хранится in-memory вместе с историей и теряется при рестарте, как и
  сами диалоги.
