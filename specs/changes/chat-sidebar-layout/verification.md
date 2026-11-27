# Verification: чат с боковой панелью «Мои истории»

Исторический оригинал: `git show 5af56b5:specs/changes/chat-sidebar-layout/verification.md`.

## Результат

- Итоговые команды: `make test` — frontend: 109 passed, 0 failed (4 новых теста `AgentApi`, 11 новых UI-тестов панели, 4 теста подсказки Кроша удалены вместе с подсказкой); backend: 279 passed, 17 skipped
- Итоговые команды: `npm --prefix frontend run build` — успешная сборка
- Итоговые команды: `docker compose ... up -d --build frontend` — страница отдаётся через Caddy на `127.0.0.1:8081`
- Итоговые команды: Headless Chrome через DevTools Protocol с cookie вошедшего пользователя `sdd_krosh` — см. таблицу viewport и ручные сценарии
- Логика `script.js` была написана до новых UI-тестов этого изменения, а не строго после падающего теста; тесты добавлены в том же изменении и проверяют все сценарии спецификации.
- Placeholder поля ввода на узких экранах сокращается многоточием.
