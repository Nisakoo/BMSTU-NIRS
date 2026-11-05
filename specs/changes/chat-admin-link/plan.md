# План: возврат из чата в панель администратора

Спецификация: [spec.md](./spec.md).

## Задача 1. Ссылка в боковой панели чата

**Требования:** REQ-001–REQ-003. В `index.html` перед `.sai-user` —
`<a class="sai-admin-link" id="saiAdminLink" href="/admin/" hidden>`.
`start()` после успешной проверки сессии ставит
`adminLink.hidden = session.user.role !== "admin"`. Стиль — как у кнопки
«+ Новая история», но контурный.

**Файлы:** `frontend/src/{index.html,script.js,styles.css}`,
`frontend/tests/ui.test.js`, `frontend/README.md`, `AGENTS.md`.

**Проверка:** `cd frontend && npm test`; пересборка frontend и CDP.
