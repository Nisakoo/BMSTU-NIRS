# План: приветствие администратора по времени суток

Спецификация: [spec.md](./spec.md).

## Задача 1. Приветствие

**Требования:** REQ-001–REQ-003.

**Решение:** экспортируемая `greetingFor(date)` в `admin.js` по часу
`date.getHours()`. `mountAdminPage` после проверки роли пишет в
`#adminGreeting` `${greetingFor(now())}, ${session.user.login}` через
`textContent`; `now` — существующий параметр страницы. В `index.html`
заголовок получает `id` и текст «Здравствуйте».

**Файлы:** `frontend/src/admin/{index.html,admin.js}`,
`frontend/tests/admin-ui.test.js`, `frontend/README.md`, `AGENTS.md`.

**Проверка:** `cd frontend && npm test`; пересборка frontend и CDP.
