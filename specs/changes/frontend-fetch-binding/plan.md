# План: сохранение контекста browser fetch

## Задача 1. Воспроизвести ошибку

**Требования:** REQ-001–REQ-003.

**Файлы:** `frontend/tests/agent-api.test.js`.

Добавить receiver-sensitive fake `fetch` для `createDialog` и
`submitMessage`; подтвердить падение `npm --prefix frontend test`.

## Задача 2. Исправить клиент

**Требования:** REQ-001–REQ-004.

**Файлы:** `frontend/src/agent-api.js`.

Привязать сохранённую функцию `fetch` к глобальному объекту при создании
`AgentApi`. Проверить Node-тесты и отсутствие изменений URL/тела.

## Задача 3. Verify

**Требования:** REQ-001–REQ-004.

**Файлы:** `specs/changes/frontend-fetch-binding/verification.md`, при
необходимости `frontend/README.md` и `docs/dialogs.md`.

Выполнить `make test`, Vite build, `test:proxy`, `git diff --check` без
браузера. Зафиксировать ограничения: browser runtime не проверялся.
