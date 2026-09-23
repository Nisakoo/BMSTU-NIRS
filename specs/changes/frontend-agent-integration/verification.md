# Проверка: интеграция frontend с агентом через Vite proxy и SSE

## Результат

Проверка завершена 22 сентября 2026 года. Frontend создаёт диалог, ожидает
`ready`, отправляет один запрос за раз и собирает SSE-фрагменты в одну реплику.
Node-тесты проверяют состояния UI, а локальный HTTP smoke подтверждает работу
Vite proxy для страницы, POST и SSE. В итоговой проверке браузер не
использовался по прямому указанию пользователя; способ проверки обновлён в
спецификации и плане.

## Проверка требований

| Требования | Доказательство | Результат |
| --- | --- | --- |
| REQ-001–REQ-003 | Vite build, `test:proxy`, ревью `vite.config.js`, FastAPI и Compose | Vite использует `frontend/src/`, `/api` проксируется в заданный `BACKEND_URL`; CORS middleware и frontend service отсутствуют |
| REQ-004–REQ-005 | `agent-api.test.js`, `ui.test.js` | Диалог создаётся при загрузке, подключается один EventSource, форма открывается только после `ready` |
| REQ-006–REQ-010 | Node-тесты HTTP-контракта и UI-состояний | POST отправляет JSON `request`; после `202` форма остаётся заблокированной до `message_end` или `message_error`; быстрые SSE-события выводятся после пользовательского сообщения; повторная отправка игнорируется |
| REQ-011–REQ-012 | Node-тесты ошибок создания/отправки, переподключения и закрытия | Ошибки дают безопасный статус, черновик остаётся при неудачном POST, EventSource закрывается при выгрузке страницы |
| REQ-013 | Node-тест тематической кнопки, autosize и Enter/Shift+Enter | Поведение сохранено; визуальная отрисовка в браузере не проверялась |
| REQ-014–REQ-015 | `make test` | Сетевой модуль тестируется с fake `fetch`/`EventSource`; 14 frontend и 132 backend теста прошли |
| REQ-016 | Vite build и `git status --short` | Production bundle собран; `node_modules/` и `dist/` игнорируются Git |
| REQ-017 | Ревью `frontend/README.md`, `docs/README.md`, `docs/dialogs.md`, `docker/README.md`, `AGENTS.md` | Раздельный запуск, proxy, in-memory/SSE-ограничения и команды описаны |

## Выполненные команды

```sh
UV_CACHE_DIR=/private/tmp/smeshariki-uv-cache UV_NO_SYNC=1 make test
npm --prefix frontend run test:proxy
npm --prefix frontend run build
UV_CACHE_DIR=/private/tmp/smeshariki-uv-cache UV_NO_SYNC=1 make lint
git diff --check
git status --short
```

Результаты: 14 frontend Node-тестов и 132 backend Pytest-теста прошли;
`test:proxy` подтвердил страницу, `201` на создание диалога и SSE с двумя
`message_delta`; Vite build и Ruff прошли, ошибок whitespace нет. Переменные
`UV_CACHE_DIR` и `UV_NO_SYNC` использованы только для доступа к уже
установленному окружению в текущей песочнице.

## Проверка границ

- Backend API и `/agent_test` не изменялись; CORS middleware не добавлен.
- Frontend не добавлен в Docker Compose, browser URL остаются относительными.
- Динамический текст выводится через `textContent`, без `innerHTML`.
- Новые тесты проверяют поведение UI и proxy; структурные тесты не добавлены.

## Известные ограничения

- Визуальная отрисовка и нативный `EventSource` в браузере не проверялись по
  указанию пользователя. Их состояния проверены в Node с fake DOM и
  EventSource, а транспорт SSE — локальным HTTP-запросом через Vite.
- Smoke-тест использует fake HTTP backend; реальный LLM endpoint и Docker-запуск
  не проверялись. Диалоги остаются in-memory, SSE replay отсутствует.
