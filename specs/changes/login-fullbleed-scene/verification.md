# Verification: страница входа без внешней рамки

Исторический оригинал: `git show 5af56b5:specs/changes/login-fullbleed-scene/verification.md`.

## Результат

- Итоговые команды: `make test` — frontend: 98 passed, 0 failed (тесты `login-ui.test.js` и `auth-api.test.js` без изменений); backend: 279 passed, 17 skipped
- Итоговые команды: `docker compose ... up -d --build frontend` — сборка Vite и Nginx успешна, страница отдаётся через Caddy
- Итоговые команды: Headless Chrome через DevTools Protocol (эмуляция viewport, замер `scrollWidth`/`scrollHeight` и элементов за краем) на `http://127.0.0.1:8081/login/` — см. таблицу viewport
- Нет.
- Frontend-тесты: 129 passed.
