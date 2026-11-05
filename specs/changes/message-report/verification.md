# Verification: жалобы на ответы агента

Спецификация: [spec.md](./spec.md), план: [plan.md](./plan.md).
Дата проверки: 2026-10-18, ветка `feat/user-dialog-history`.

## Команды

| Команда | Результат |
| --- | --- |
| `make test` | frontend: 174 passed; backend: 380 passed, 33 skipped (тесты PostgreSQL/Redis без `TEST_*_URL`) |
| `TEST_DATABASE_URL=… pytest backend/tests/integration/db` на временном `postgres:17-alpine` | 30 passed |
| `make lint` | 101 файл отформатирован, `All checks passed!` |
| `npx vite build` | сборка успешна |
| `make migrate` на Compose-базе | `alembic_version` = `0006`, таблица `message_reports` со всеми ограничениями и индексом |

## Порядок TDD и отклонения

**Тесты, которые падали до реализации:**

- PostgreSQL-хранилище — сбор тестов падал на импорте `ReportExistsError`;
- сервис и API пользователя — 20 тестов;
- домен и API администратора — сбор тестов падал на импорте;
- клиент API чата — 5 тестов, UI чата — 9 тестов;
- клиент API админки — 6 тестов, UI админки — файл не загружался без `mountReports`.

**Отклонения:**

- `InMemoryHistoryStore.report` написан в задаче 1 вместе с контрактом
  (абстрактный метод иначе ломает создание хранилища). Поэтому его модульные
  тесты в задаче 2 прошли сразу, без шага RED. Для проверок в тестах у него
  есть метод `reports()`.
- Первая версия `PostgresHistoryStore.report` отдельно ловила
  `IntegrityError`. Это лишнее: `ON CONFLICT (message_id) DO NOTHING` и так
  превращает повтор, в том числе параллельный, в отсутствие строки. Обработка
  удалена, тесты остались зелёными.
- Существующий тест `test_answered_dialog_is_listed_and_its_messages_are_returned`
  фиксировал точный набор полей сообщения; в него добавлено поле `reported`
  (REQ-006).
- В журнал разрешены поля `report_id` и `status` (`_SAFE_FIELDS`).
- В UI-тестах админки уже был помощник `find`; мой дубликат удалён.
- Ошибки раздела «Жалобы» показываются в собственной строке
  `#adminReportsError` раздела, а не в общем блоке ошибки панели: сбой жалоб
  не должен скрывать статистику.
- При ручной проверке на 390px кнопки фильтра жалоб наезжали друг на друга
  в одной строке с заголовком. До 620px фильтр стоит под заголовком сеткой
  2×2.

## Ручная проверка

Проверка через CDP в headless Chrome на `127.0.0.1:8081` после пересборки
backend и frontend и `make migrate`. Пользователь `sdd_copy` создан при
проверке копирования. Администратор `sdd_reports_admin` зарегистрирован через
API, и роль `admin` выдана ему SQL-запросом в локальной базе. В локальной базе
остались эти два пользователя и одна жалоба в статусе `new`.

**Чат (1280px и 390px):**

- У сохранённого ответа флажок «Пожаловаться», панель открывается, фокус на
  «Страшно», «Отправить» недоступна без причины.
- `Escape` закрыл панель и вернул фокус на флажок.
- «Грубо или обидно» с комментарием «Ёжика назвали глупым» — «Жалоба
  отправлена», строка состояния «Спасибо! Взрослые посмотрят».
- История: `reported` = `[false, true]`. Повторный `POST` — `409`, жалоба на
  сообщение пользователя — `404`.
- На телефоне после перезагрузки флажок восстановлен как «Жалоба
  отправлена». Панель на новом ответе — 320px, `scrollWidth` 390.

**Админка:**

- Счётчик «Жалобы 1» в навигации, активен раздел `#reports`.
- Карточка: «Грубо или обидно | Новая | сегодня, 19:15 | «Ёжика назвали
  глупым» | Запрос | Ответ», кнопки «Рассмотрено» и «Отклонить».
- «Рассмотрено»:
  - список новых — «Жалоб нет», счётчик скрыт;
  - в базе `resolved`, `resolved_at` и `resolved_by` заполнены.
- Пользователь удалил историю (`204`). В фильтре «Все» карточка с пометкой
  «история удалена» и полным текстом ответа.
- «Вернуть в новые»:
  - статус «Новая», счётчик 1;
  - в базе `new`, `resolved_at` и `resolved_by` — `NULL`, `message_id` — `NULL`.
- Телефон 390px: фильтр 2×2, `scrollWidth` 390.

**Журнал backend:** есть `dialog.report.created` и
`admin.report.status_changed`; ни текста комментария, ни запроса, ни ответа в
журнале нет.

Первая попытка «Вернуть в новые» в скрипте проверки не сработала: из-за
`scroll-behavior: smooth` координаты брались до конца прокрутки. Это ошибка
скрипта, а не продукта. Повтор с мгновенной прокруткой прошёл.

Скриншоты лежат в `~/Desktop/макеты-смешарики/жалобы/`.

## Требования

| Требование | Проверка | Результат |
| --- | --- | --- |
| REQ-001 | `test_report_copies_the_answer_and_its_request`; `\d message_reports` после `make migrate` | Выполнено |
| REQ-002 | `test_report_outlives_the_deleted_dialog` (PostgreSQL и in-memory); ручная проверка «история удалена» | Выполнено |
| REQ-003 | `test_report_is_created_once_and_marks_the_answer`, `test_missing_or_blank_comment_is_stored_as_none`, `test_comment_of_500_characters_is_accepted`, `test_invalid_report_returns_422` | Выполнено |
| REQ-004 | `test_one_report_per_answer_of_the_owner`; API `409`; ручная проверка | Выполнено |
| REQ-005 | `test_only_own_answers_can_be_reported`, `test_report_on_missing_dialog_is_404`, `test_guest_gets_401_before_validation`, `test_unavailable_store_returns_503` | Выполнено |
| REQ-006 | Флаги `reported` в тестах хранилищ; `test_answered_dialog_is_listed…`; клиент «getMessages reads…» | Выполнено |
| REQ-007 | UI «a report flag sits under a finished answer»; у ответа с ошибкой нет строки оценки («an answer that failed…») | Выполнено |
| REQ-008 | UI «the report panel offers reasons…», «…closes by its cancel button or escape», «only one report panel is open at a time» | Выполнено |
| REQ-009 | UI «a sent report (201/409)…», «a failed report keeps the panel…», «a 401 on report refreshes…» | Выполнено |
| REQ-010 | UI «a saved story shows which answers were reported»; ручная проверка на телефоне | Выполнено |
| REQ-011 | `test_admin_lists_new_reports_with_texts_but_no_author`, `test_reports_are_filtered_by_status`, `test_reports_are_listed_newest_first_by_status` (лимит, порядок, `dialog_deleted`) | Выполнено |
| REQ-012 | `test_admin_changes_the_status`, `test_unknown_report_is_404`, `test_reopened_report_forgets_who_closed_it` | Выполнено |
| REQ-013 | `test_admin_receives_user_statistics` (`reports_new`), `reports_new` в PostgreSQL-тесте | Выполнено |
| REQ-014 | `test_guest_and_user_are_rejected_before_validation`, `test_admin_with_invalid_input_gets_422`, `test_unavailable_storage_returns_503`, `test_missing_reports_service_returns_503` | Выполнено |
| REQ-015 | UI админки: список, фильтр, смена статуса и счётчик, пустой список, ошибки, «the admin page shows the number of new reports…»; ручная проверка | Выполнено |
| REQ-016 | `test_report_is_delegated_and_logged_without_texts`, `test_status_change_is_logged_without_texts`, `test_logs_do_not_contain_report_texts`; журнал Compose; fake DOM запрещает `innerHTML` | Выполнено |

## Критерии приёмки

- [x] Под завершёнными ответами есть «Пожаловаться» с выбором причины;
  жалоба сохраняется, повтор невозможен, состояние восстанавливается из истории.
- [x] API жалобы отвечает по REQ-003–REQ-005; чужой ответ — `404`.
- [x] Раздел «Жалобы» в `/admin/` показывает жалобы с текстами, фильтр и смену
  статуса; счётчик новых жалоб корректен.
- [x] Жалоба остаётся у администратора после удаления истории пользователем.
- [x] `make migrate` применяет `0006` без потери данных.
- [x] `make test` и `make lint` проходят успешно.

## Документация

Обновлены `docs/dialogs.md` (ручка жалобы, поле `reported`, раздел о
жалобах), `docs/database.md` (таблица `message_reports`), `docs/admin.md`
(раздел «Жалобы на ответы», `reports_new`, реализация), `docs/README.md`,
`frontend/README.md`, `AGENTS.md`.
