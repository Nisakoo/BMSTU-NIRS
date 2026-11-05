# Verification: dialog-history-repair

Дата: 2026-11-05. Ветка `fix/dialog-history-regressions` от `main` (`97f24c0`).

## Требования

| Требование | Проверка | Результат |
| --- | --- | --- |
| REQ-001 | `test_message_feedback.py::test_invalid_feedback_returns_422` (`0`, `-1`, `2**63`, `99999999999999999999`), `test_out_of_range_message_id_is_422_without_storage` (хранилище ответило бы `503`), `test_message_report.py::test_invalid_report_returns_422` (`0`, `2**63`), `test_report_news.py::test_invalid_seen_body_returns_422` (`[0]`, `[2**63]`), `test_admin_reports.py::test_admin_with_invalid_input_gets_422` (`/reports/0`, `/reports/2**63`). До исправления 12 из этих случаев падали (`404`/`204` вместо `422`). | Пройдено |
| REQ-002 | Существующие `test_guest_gets_401_before_validation` (feedback, report, news) и `test_guest_and_user_are_rejected_before_validation` (admin). | Пройдено |
| REQ-003 | `make test` на Node v24.22.2 (с `navigator.locks`): 219/219 frontend-тестов. Заглушка `no-web-locks.js` убирает `navigator.locks`, поэтому на Node 22 без Web Locks поведение тестов то же. | Пройдено |
| REQ-004 | Ревью: пометка «Не действует» в начале `specs/changes/dialog-history/spec.md` со ссылками на `user-dialog-history` и это изменение; статусы других спецификаций не менялись. | Пройдено |
| REQ-005 | Ревью: диапазон 1…2⁶³−1 указан в `docs/dialogs.md` (оценки, жалобы, `report_ids`) и `docs/admin.md` (`PATCH /reports/{id}`). | Пройдено |

## Команды

- `make lint` — `All checks passed!`, `142 files already formatted`.
- `make test` — frontend 219 passed, 0 failed; backend 751 passed, 103 skipped.

- `make test-integration` (одноразовые PostgreSQL и Redis) — 854 passed,
  0 skipped.
- Запуск стека Compose (`up --build`): все сервисы healthy, `migrate`
  завершился с кодом 0, версия базы `0009`. Smoke-тест через Caddy
  (`127.0.0.1:8080`): `/`, `/login/`, `/admin/` — `200`; регистрация `201`,
  вход `200`, `POST /dialogs` `201`, список и история `200`; `PUT`/`DELETE
  feedback` и `POST report` с `message_id` `0`, `2**63`,
  `99999999999999999999` — `422`; `report_ids: [2**63]` — `422`; гость —
  `401`; `PATCH /admin/reports/2**63` от пользователя — `403`; удаление
  диалога `204`, выход `204`.

## Ограничения

- Node 22 локально не запускался.
- Вне scope найдено: при запуске с `deepseek/deepseek-flash` модель
  возвращает несколько параллельных tool calls, `LiteLLMProvider` отклоняет
  такой ответ (`TypeError: Only one tool call is supported.` →
  `LLMProviderError`), и агент не отвечает. `parallel_tool_calls=False`
  модель игнорирует. Ограничение одного tool call зафиксировано в
  `litellm-provider` в разделе «Сначала спросить», поэтому здесь не меняется.
- Пустые диалоги в базе и лимит списка в 50 диалогов сознательно оставлены
  поведением `user-dialog-history`.
