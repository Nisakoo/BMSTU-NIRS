# План: дата регистрации вместо статуса пользователя

Спецификация: [spec.md](./spec.md).

## Задача 1. Колонка «Регистрация»

**Требования:** REQ-001–REQ-004.

**Решение:** `formatDay(timestamp, now)` в `admin.js` по тем же правилам,
что `formatActivity`, но без времени; `formatActivity` использует его для
даты. В `renderUsers` вместо `adm-user-status` — `adm-user-cell` с датой
регистрации. Заголовок колонки — «Регистрация». Стили
`.adm-user-status*` удаляются.

**Файлы:** `frontend/src/admin/{admin.js,index.html,admin.css}`,
`frontend/tests/admin-ui.test.js`, `docs/admin.md`, `frontend/README.md`.

**Проверка:** `cd frontend && npm test`; пересборка frontend и CDP на 1280 и
390 px.
