# Verification: «Настройки» со сменой пароля в админке

Спецификация: [spec.md](./spec.md). План отдельно не выделялся: вынос логики
окна в модуль и подключение в админке.

| Проверка | Результат |
| --- | --- |
| `npm --prefix frontend test` | 214 passed: 98 тестов чата без изменений, 6 новых тестов админки |
| `npx vite build` | Сборка успешна |
| Headless Chrome 1440×1000 и 600×900, `/admin/` с подставным API | Кнопка «Настройки» над «Выйти»; на узком экране — рядом с «Выйти»; окно открывается по центру |
| `docker compose up -d --build frontend` | Отданная `/admin/` содержит кнопку |

| Требование | Чем подтверждено |
| --- | --- |
| REQ-001 | Скриншоты; ревью разметки и CSS |
| REQ-002 | `the admin settings window opens and closes like in the chat`, `the admin password form checks fields locally and saves a new password`, `a wrong admin current password is reported` |
| REQ-003 | `a 401 on the admin password change refreshes once and retries`, `an admin password change without a session opens the login page` |
| REQ-004 | Модуль `password-settings.js`; UI-тесты чата проходят без изменений |
| REQ-005 | `the settings window is not mounted for a regular user` |

## Ограничения

- В живом стеке с входом администратора не проверялось: нет пароля
  администратора.
