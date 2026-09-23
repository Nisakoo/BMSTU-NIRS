# Frontend

Frontend `smeshariki-ai` — vanilla JavaScript приложение. В основном запуске
его собирает Vite, раздаёт Nginx, а Caddy направляет `/api` и SSE в backend.
Vite proxy остаётся отдельным режимом локальной разработки.

## Состав

- `src/index.html` — главная страница чата;
- `src/styles.css` — стили страницы;
- `src/script.js` — DOM и состояния пользовательского интерфейса;
- `src/agent-api.js` — HTTP/SSE-клиент без зависимости от DOM;
- `src/static/characters/` — изображения персонажей;
- `tests/` — детерминированные Node-тесты сетевого контракта и состояний UI;
- `vite.config.js` — root, build output и proxy `/api`;
- `package.json` и `package-lock.json` — npm-команды и зафиксированные
  зависимости.

## Основной запуск

Из корня репозитория настройте `docker/.env` по шаблону
`docker/.env.example`, затем выполните:

```sh
make run
```

Откройте `http://localhost:8080/` (или порт из `APP_PORT`). Frontend, Caddy и
backend работают в одном Compose проекте; отдельные `npm ci` и `make frontend`
для этого сценария не требуются. Все браузерные запросы остаются на одном
origin. Caddy передаёт `/api/*` в backend, а статические файлы — Nginx.

## Vite dev-режим

Установите frontend-зависимости один раз:

```sh
npm --prefix frontend ci
```

Для Vite proxy нужен доступный на хосте API. После `make run` он доступен через
Caddy на `127.0.0.1:8080`, поэтому запустите Vite так:

```sh
BACKEND_URL=http://127.0.0.1:8080 make frontend
```

Откройте [`http://127.0.0.1:5173/`](http://127.0.0.1:5173/).

Vite принимает браузерные запросы `/api/*` на своём origin и проксирует их в
backend. Default target при запуске без `BACKEND_URL` —
`http://127.0.0.1:8000`, если backend запущен отдельно. Для другого адреса
задайте переменную процесса Vite:

```sh
BACKEND_URL=http://127.0.0.1:9000 make frontend
```

FastAPI не включает CORS middleware: и в основном запуске, и в Vite dev-режиме
браузер обращается к API через тот же origin, с которого загружена страница.

## Команды

```sh
npm --prefix frontend run dev
npm --prefix frontend test
npm --prefix frontend run test:proxy
npm --prefix frontend run build
```

`test:proxy` проверяет локальный Vite proxy для HTTP и SSE с временным fake
backend без браузера.

Сетевой клиент сохраняет корректный контекст вызова browser `fetch`; Node-тесты
проверяют этот случай отдельно, поскольку обычный fake `fetch` его не выявляет.

Production bundle создаётся в игнорируемом каталоге `frontend/dist/`.

## Диалоговый поток

При загрузке frontend создаёт новый in-memory диалог и открывает `EventSource`.
Поле ввода доступно только после события `ready`. Сообщение отправляется через
`POST /api/v1/dialogs/{dialog_id}/messages`, а ответ собирается из
`message_start`, `message_delta`, `message_end` и `message_error`.
Если создание диалога временно не удалось, форма остаётся заблокированной,
а frontend повторяет попытку каждые три секунды. После восстановления backend
страницу перезагружать не нужно.

Frontend допускает один незавершённый запрос, буферизует быстрые SSE-события до
получения `202 Accepted` и вставляет пользовательский и модельный текст только
через `textContent`.

## Ограничения

- Диалог и история хранятся только в памяти backend и теряются при рестарте.
- Перезагрузка страницы создаёт новый диалог; browser persistence отсутствует.
- SSE не поддерживает replay, поэтому потерянные при разрыве события не
  восстанавливаются.
- Основной Compose запуск использует локальный HTTP без публичного домена и
  автоматического HTTPS. Vite proxy остаётся только dev-контрактом.

Требования интеграции находятся в
[`spec.md`](../specs/changes/frontend-agent-integration/spec.md), порядок работ —
в [`plan.md`](../specs/changes/frontend-agent-integration/plan.md), результаты
проверки — в
[`verification.md`](../specs/changes/frontend-agent-integration/verification.md).

Повторное создание диалога после временной ошибки описано в
[`spec.md`](../specs/changes/frontend-dialog-retry/spec.md) и
[`verification.md`](../specs/changes/frontend-dialog-retry/verification.md).
Исправление browser `fetch` описано в
[`spec.md`](../specs/changes/frontend-fetch-binding/spec.md) и
[`verification.md`](../specs/changes/frontend-fetch-binding/verification.md).
Единый контейнерный запуск описан в
[`spec.md`](../specs/changes/compose-caddy-nginx-stack/spec.md), его проверка — в
[`verification.md`](../specs/changes/compose-caddy-nginx-stack/verification.md).
