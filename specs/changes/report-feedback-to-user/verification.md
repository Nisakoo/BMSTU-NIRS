# Verification: ответ пользователю о разборе жалобы

Спецификация: [spec.md](./spec.md), план: [plan.md](./plan.md).
Дата проверки: 2026-10-18, ветка `feat/user-dialog-history`.

## Команды

| Команда | Результат |
| --- | --- |
| `make test` | frontend: 183 passed; backend: 397 passed, 36 skipped (тесты PostgreSQL/Redis без `TEST_*_URL`) |
| `TEST_DATABASE_URL=… pytest backend/tests/integration/db` на временном `postgres:17-alpine` | 33 passed |
| `make lint` | `All checks passed!`, 103 файла отформатированы |
| `npx vite build` | сборка успешна |
| `make migrate` на Compose-базе | `alembic_version` = `0007` |

## Порядок TDD и отклонения

**Тесты, которые падали до реализации:**

- PostgreSQL — сбор тестов падал на импорте `ReportNews`/`ReportState`;
- сервис и API — 17 тестов;
- клиент API чата — 5 тестов, UI чата — 6 тестов.

**Отклонения:**

- `InMemoryHistoryStore.report_news` и `mark_report_news_seen` написаны в
  задаче 1 вместе с контрактом (иначе абстрактный класс не создаётся).
  Поэтому их модульный тест прошёл сразу, без RED.
- Вместо отдельного роутера `/api/v1/reports` ручки новостей добавлены в
  существующий роутер `/api/v1` с `current_user`: эффект тот же (`401`
  раньше `422`), кода меньше.
- `StoredMessage.reported` стал свойством от `report`, поэтому старый код и
  тесты не менялись. Клиент API чата отдаёт `report`, а если пришёл только
  старый `reported: true` — `"sent"`.
- В журнал разрешено поле `count`.
- В UI-стенде у `#saiNews` выставлен начальный `hidden`, как в разметке
  страницы; без этого два теста видели плашку изначально открытой.

## Ручная проверка

Проверка через CDP в headless Chrome на `127.0.0.1:8081` после пересборки и
`make migrate`; пользователь `sdd_copy`, администратор `sdd_reports_admin`.

- До разбора новая жалоба в новости не попадает.
- После «Рассмотрено» и «Отклонить» для двух жалоб:
  - в `GET /api/v1/reports/news` две новости, слов `resolved` и `dismissed`
    в ответе нет;
  - при открытии чата плашка «Взрослые посмотрели твои жалобы (2). Спасибо,
    что рассказал!» с одной кнопкой «Хорошо», форма доступна.
- «Хорошо»: плашка скрыта, новости пусты, после перезагрузки плашки нет.
- Админ вернул жалобу в «новые» и снова отклонил. Телефон 390px:
  - плашка «…твою жалобу на историю «Одной фразой: Нюша рисует радугу»…» с
    кнопками «Хорошо» и «Открыть историю», `scrollWidth` 390;
  - «Открыть историю» открыла эту историю, флажок «Взрослые посмотрели —
    спасибо!», новости пусты.
- Журнал: два события `dialog.report.news_seen`, названий историй в
  журнале нет.

**Ошибка при проверке:** мой скрипт выбирал «любую другую жалобу» и по
ошибке поставил «Рассмотрено» жалобе №3 пользователя `ksu`, а не тестовой
жалобе. Я вернул жалобу №3 в `new` SQL-запросом (`resolved_at`,
`resolved_by` и `seen_at` — `NULL`). Её исходный статус по журналу
восстановить нельзя (журнал backend обнулился при пересборке), но «новая» —
наиболее вероятное состояние. Жалоба №1 была отклонена аккаунтом `admin` в
16:23, ещё до проверки.

Скриншоты лежат в `~/Desktop/макеты-смешарики/жалобы/` (60–62).

## Требования

| Требование | Проверка | Результат |
| --- | --- | --- |
| REQ-001 | `make migrate` (`0007`); PostgreSQL-тесты | Выполнено |
| REQ-002 | `test_reviewed_again_report_is_news_again`; in-memory тест; ручная проверка | Выполнено |
| REQ-003 | `test_news_are_reviewed_unseen_reports_of_the_owner`, `test_news_of_a_deleted_story_has_no_dialog`, `test_news_name_the_story_and_hide_the_outcome`, `test_news_of_a_deleted_story_have_no_dialog` | Выполнено |
| REQ-004 | `test_seen_news_do_not_come_back_and_others_are_skipped`, `test_invalid_seen_body_returns_422`; отметка в PostgreSQL-тесте | Выполнено |
| REQ-005 | `test_guest_gets_401_before_validation`, `test_unavailable_store_returns_503` | Выполнено |
| REQ-006 | `test_news_name_the_story_and_hide_the_outcome`, `test_new_story_has_no_report_and_no_news`, `test_answered_dialog_is_listed…`; клиент «getMessages reads…» | Выполнено |
| REQ-007 | UI «one reviewed report greets…», «several reports are counted and a deleted story is not named» | Выполнено |
| REQ-008 | UI «…greets…» («Хорошо»), «the banner opens the reviewed story», «news failures stay silent…» | Выполнено |
| REQ-009 | UI «news failures stay silent and the banner comes once per page», «no news means no Krosh banner», «a guest never asks for news» | Выполнено |
| REQ-010 | UI «the banner opens the reviewed story» (`is-reviewed`), «a saved story shows which answers were reported» | Выполнено |
| REQ-011 | Название с `<b>` выводится как текст (UI-тест); ревью: только `textContent` | Выполнено |
| REQ-012 | `test_report_news_are_read_and_marked_seen_with_a_count`; журнал Compose | Выполнено |

## Критерии приёмки

- [x] После разбора жалобы при открытии чата появляется плашка Кроша без
  поиска истории; подпись одна для «Рассмотрено» и «Отклонить».
- [x] «Хорошо» убирает новость навсегда, пока жалобу снова не разберут после
  возврата в «новые»; «Открыть историю» открывает нужную историю.
- [x] Под разобранным ответом подпись «Взрослые посмотрели — спасибо!».
- [x] API не раскрывает пользователю `resolved`/`dismissed`.
- [x] `make migrate` применяет `0007` без потери данных.
- [x] `make test` и `make lint` проходят успешно.

## Документация

Обновлены `docs/dialogs.md`, `docs/database.md`, `docs/admin.md`,
`docs/README.md`, `frontend/README.md`, `AGENTS.md`.
