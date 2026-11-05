# Verification: смена пароля в настройках аккаунта

Спецификация: [spec.md](./spec.md), план: [plan.md](./plan.md).

## Команды

| Команда | Результат |
| --- | --- |
| `make test` | frontend: 201 passed; backend: 423 passed, 40 skipped (тесты PostgreSQL без `TEST_DATABASE_URL`) |
| `TEST_DATABASE_URL=… pytest backend/tests/integration/db` на временном `postgres:17-alpine` | 37 passed |
| `make lint` | All checks passed, 103 files already formatted |
| `npx vite build` (в `frontend/`) | Сборка успешна |
| Headless Chrome, 1280×800 и 520×844, окно открыто вручную в копии сборки | Окно по центру, помещается по ширине, ошибка видна под полями |

## Требования

| Требование | Чем подтверждено |
| --- | --- |
| REQ-001 | `test_change_password_replaces_hash_for_later_logins`, `test_change_password_switches_login_to_the_new_password`, `test_user_store_reads_and_replaces_password_hash` |
| REQ-002 | `test_change_password_invalid_body_returns_422_without_echo` (7 тел), `test_change_password_rejects_the_same_password`, `test_change_password_rejects_the_same_password_after_checking_it` |
| REQ-003 | `test_change_password_rejects_wrong_current_password` (unit и API) |
| REQ-004 | `test_change_password_requires_session_before_validation`, `test_change_password_requires_a_valid_access_token`, `test_change_password_fails_closed_when_storage_is_unavailable` |
| REQ-005 | `test_change_password_keeps_current_session_and_revokes_others`, `test_change_password_signs_out_other_sessions_only`, `test_revoke_user_sessions_keeps_one_session_and_other_users` |
| REQ-006 | `test_change_password_logs_events_without_passwords`, `test_change_password_logs_no_passwords` |
| REQ-007 | API-тесты сравнивают тело ошибки целиком (`{"error": ...}`) |
| REQ-008 | Ревью `index.html`: кнопка `aria-label`/`title` «Настройки» между логином и «Выйти»; скриншот |
| REQ-009 | `the gear opens settings and the window closes by button, escape or backdrop`, `a click inside the settings card keeps the window open`; ревью разметки (`role="dialog"`, `aria-modal`) |
| REQ-010 | `the password form checks its fields before sending anything` |
| REQ-011 | `a changed password clears the fields…`, `a wrong current password is cleared and focused`, `every other password answer gets its own message`, `the settings window is locked while the password is saved`, `a 401 on password change refreshes…`, `a password change without a session opens the login page`; `changePassword` тесты в `auth-api.test.js` |
| REQ-012 | Сообщения через `textContent`, область `aria-live` в разметке; `passwords never reach browser storage` |
| REQ-013 | Скриншот 520×844: окно помещается по ширине; карточка `width:min(420px,100%)` при отступе 16px |
| REQ-014 | `settings keep the answer streaming and the dialog connected` |

Документация обновлена: `docs/auth.md`, `docs/README.md`,
`frontend/README.md`, `AGENTS.md`.

## Ограничения

- Полный `make run` с живым backend не запускался; поведение проверено
  тестами на ASGI-приложении, in-memory и PostgreSQL-адаптерах.
- Headless Chrome не уменьшает окно меньше ~500px, поэтому ширина 390px
  проверена расчётом CSS, а не скриншотом.
- Ветка не слита с `main`: при слиянии к ручке нужно применить проверки из
  `auth-hardening` и `auth-rate-limit` (`Sec-Fetch-Site`, `415`, rate
  limiting).
- Выданные ранее access-токены других устройств действуют до своего
  истечения (до 15 минут), как и задано REQ-005.
