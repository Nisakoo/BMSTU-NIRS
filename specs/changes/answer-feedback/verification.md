# Verification: оценка ответов агента и качество в панели администратора

Спецификация: [spec.md](./spec.md), план: [plan.md](./plan.md).
Дата проверки: 2026-10-17, ветка `feat/user-dialog-history`.

## Итоговые команды

| Команда | Результат |
| --- | --- |
| `make test` | frontend: 129 passed, 0 failed; backend: 324 passed, 22 skipped (интеграционные тесты PostgreSQL/Redis без `TEST_*_URL`) |
| `make lint` | `All checks passed!`, 93 файла отформатированы |
| `TEST_DATABASE_URL=… pytest backend/tests/integration/db` на временном `postgres:17-alpine` | 19 passed (3 новых теста оценок в `PostgresHistoryStore`, 2 новых теста статистики оценок) |
| `npm --prefix frontend run build` | успешно |
| `docker compose ... up -d --build`, сервис `migrate` | `alembic_version = 0003`, таблица `message_feedback` создана, данные сохранились |

Порядок TDD соблюдён во всех задачах: новые тесты сначала падали, затем
прошли. Старые тесты, сравнивавшие `message_end` целиком и историю без `id`,
обновлены под новый контракт.

## Ручная проверка

Compose-стек на `127.0.0.1:8081`, пользователь `sdd_krosh` и администратор
`sdd_admin` (создан `python -m smeshariki_ai.create_admin`):

- в чате через headless Chrome открыты две сохранённые истории, первому
  ответу поставлен 👍, второму — 👎; `GET .../messages` вернул `like` и
  `dislike`, после повторного открытия кнопки отражают сохранённые оценки;
- найден и исправлен дефект: кнопки оценки последнего ответа оказывались под
  полем ввода, так как лента прокручивалась до добавления кнопок; после
  исправления (`scrollTop` после вставки) кнопки видны;
- `/admin/` за 30 дней: «Положительные оценки 50%», «оценено 2 из 7
  ответов», 👍 1, 👎 1, индикатор заполнен наполовину, метки «демо-данные» у
  блока нет.

## Требования

| Требование | Проверка | Результат |
| --- | --- | --- |
| REQ-001 | Миграция `0003`; `test_postgres_history.py`: `test_append_returns_ids_and_feedback_is_stored`, `test_deleting_a_user_removes_feedback`; ревью `CHECK` и PK | Выполнено |
| REQ-002 | `test_message_feedback.py::test_feedback_is_set_changed_and_cleared` (`204` на установку, смену и двойное снятие) | Выполнено |
| REQ-003 | `test_only_own_answers_can_be_rated` (сообщение пользователя, несуществующее, другого диалога, чужого пользователя), `test_feedback_on_missing_dialog_is_404`, `test_invalid_feedback_returns_422`, `test_guest_gets_401_before_validation`, `test_unavailable_store_returns_503`; хранилища: `test_feedback_targets_only_own_assistant_answers` (память и PostgreSQL) | Выполнено |
| REQ-004 | `test_dialog_history.py` (набор полей с `id` и `feedback`); `test_feedback_is_set_changed_and_cleared` | Выполнено |
| REQ-005 | `test_agent_service.py::test_message_end_carries_the_saved_answer_id`; `test_sse.py` (`message_end` с `{"message_id":2}`) | Выполнено |
| REQ-006 | `ui.test.js`: `rating buttons appear only under a finished answer`, `an answer that failed or has no id gets no rating buttons`; скриншот | Выполнено |
| REQ-007 | `rating toggles, switches and clears an answer` | Выполнено |
| REQ-008 | `a failed rating is rolled back with a message`, `a 401 on rating refreshes the session and retries once` | Выполнено |
| REQ-009 | `a saved story shows its stored ratings`; ручная проверка | Выполнено |
| REQ-010 | `test_admin_stats.py` (точный JSON с `feedback`), `test_admin_stats_service.py` (передача и нулевые значения), `test_postgres_admin_stats.py::test_feedback_counts_answers_and_ratings_in_the_window` (окно, старые ответы не считаются), `test_feedback_is_zero_without_answers` | Выполнено |
| REQ-011 | `admin-ui.test.js`: `answer quality shows the real share of likes for the period`, `answer quality without ratings says so`, `only agent figures carry the demo label`; `admin-api.test.js`: разбор и отказ при несогласованных числах; ревью `index.html` (метка снята, подсказка обновлена); `admin-data.test.js`: демо-данные без метрик качества | Выполнено |
| REQ-012 | `changing the period reloads answer quality`; ревью: в блок выводятся только числа | Выполнено |
| REQ-013 | Ревью: события `dialog.feedback.set` и `dialog.feedback.cleared` с `dialog_id`, `message_id`, `feedback`; поля добавлены в разрешённые; тексты не журналируются | Выполнено |

## Документация

Ревью: `docs/dialogs.md`, `docs/database.md`, `docs/admin.md`,
`docs/README.md`, `frontend/README.md`, `AGENTS.md`.

## Известные ограничения

- Регрессионный автоматический тест прокрутки к кнопкам оценки невозможен на
  fake DOM (нет реальной высоты ленты); исправление подтверждено скриншотом.
- В локальной базе созданы тестовые учётные записи `sdd_krosh`, `sdd_nyusha`
  и администратор `sdd_admin` (пароль `password123`).
