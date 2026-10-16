# Verification: кнопка выхода в чате и панели администратора

Спецификация: [spec.md](./spec.md), план: [plan.md](./plan.md).
Дата проверки: 2026-10-16, ветка `feat/auth-guard`.

## Итоговые команды

| Команда | Результат |
| --- | --- |
| `make lint` | `All checks passed!`, 77 файлов отформатированы |
| `make test` | frontend: 88 passed, 0 failed; backend: 232 passed, 7 skipped (интеграционные PostgreSQL/Redis без `TEST_*_URL`, как до изменения) |
| `npm --prefix frontend run build` | успешная сборка |

## Требования

| Требование | Проверка | Результат |
| --- | --- | --- |
| REQ-001 | Разметка `#saiLogout` в шапке чата; скриншоты headless Chrome на 1280px и 375px: кнопка видна справа от статуса и не перекрывает форму | Выполнено |
| REQ-002 | Разметка `#adminLogout` в `.adm-sidebar-foot`; скриншоты на 1280px (низ боковой панели), 700px и 375px (правый верхний угол панели) | Выполнено |
| REQ-003 | `ui.test.js`: `logout locks the button and ignores repeated clicks`; `admin-ui.test.js`: `admin logout locks the button…` | Выполнено |
| REQ-004 | `ui.test.js`: `logout ends the session, closes the stream…`, `logout cancels a pending dialog retry`; `admin-ui.test.js`: `an administrator logs out…` | Выполнено |
| REQ-005 | `ui.test.js`: `a failed logout keeps the chat…` (`503` и сетевой сбой); `admin-ui.test.js`: `a failed admin logout keeps the panel…`; правило `.sai-status[data-state="error"]` для ≤570px подтверждено скриншотом | Выполнено |
| REQ-006 | Ревью `script.js` и `admin.js`: используется только `AuthApi.logout()`, cookie и Web Storage не затрагиваются | Выполнено |
| REQ-007 | Ревью `docs/auth.md` (раздел «Выход», пункт удалён из «Что пока не реализовано»), `frontend/README.md`, `AGENTS.md` | Выполнено |

Дополнительно: `admin-ui.test.js` `logout is not wired for visitors who are
redirected away` подтверждает, что обработчик подключается только для роли
`admin`.

## Известные ограничения

- Скриншоты сняты на Vite dev server без backend, поэтому страницы находились в
  состоянии «сервис недоступен»; на расположение кнопок это не влияет.
- Сквозной выход в браузере против запущенного backend не выполнялся.
  `POST /api/v1/auth/logout` покрыт существующими backend-тестами
  (`test_auth.py`), а поведение кнопок — Node-тестами с fake `fetch` и
  `location`.
