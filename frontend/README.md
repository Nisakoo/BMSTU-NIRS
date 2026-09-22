# Frontend

Frontend `smeshariki-ai` — отдельное vanilla JavaScript приложение, которое
через Vite proxy использует dialog API и SSE-поток backend.

## Состав

- `src/index.html` — главная страница чата;
- `src/styles.css` — стили страницы;
- `src/script.js` — DOM и состояния пользовательского интерфейса;
- `src/agent-api.js` — HTTP/SSE-клиент без зависимости от DOM;
- `src/static/characters/` — изображения персонажей;
- `tests/` — детерминированные Node-тесты сетевого контракта;
- `vite.config.js` — root, build output и proxy `/api`;
- `package.json` и `package-lock.json` — npm-команды и зафиксированные
  зависимости.

## Локальный запуск

Установите frontend-зависимости один раз:

```sh
npm --prefix frontend ci
```

В первом терминале запустите backend:

```sh
make run
```

Во втором терминале запустите frontend:

```sh
make frontend
```

Откройте [`http://127.0.0.1:5173/`](http://127.0.0.1:5173/).

Vite принимает браузерные запросы `/api/*` на своём origin и проксирует их в
backend. Default target — `http://127.0.0.1:8000`. Для другого адреса задайте
переменную процесса Vite:

```sh
BACKEND_URL=http://127.0.0.1:9000 make frontend
```

Frontend не входит в Docker Compose, а FastAPI не включает CORS middleware для
этого сценария.

## Команды

```sh
npm --prefix frontend run dev
npm --prefix frontend test
npm --prefix frontend run build
```

Production bundle создаётся в игнорируемом каталоге `frontend/dist/`.

## Диалоговый поток

При загрузке frontend создаёт новый in-memory диалог и открывает `EventSource`.
Поле ввода доступно только после события `ready`. Сообщение отправляется через
`POST /api/v1/dialogs/{dialog_id}/messages`, а ответ собирается из
`message_start`, `message_delta`, `message_end` и `message_error`.

Frontend допускает один незавершённый запрос, буферизует быстрые SSE-события до
получения `202 Accepted` и вставляет пользовательский и модельный текст только
через `textContent`.

## Ограничения

- Диалог и история хранятся только в памяти backend и теряются при рестарте.
- Перезагрузка страницы создаёт новый диалог; browser persistence отсутствует.
- SSE не поддерживает replay, поэтому потерянные при разрыве события не
  восстанавливаются.
- Vite proxy является локальным development contract. Production routing и
  deployment frontend согласуются отдельно.

Требования интеграции находятся в
[`spec.md`](../specs/changes/frontend-agent-integration/spec.md), порядок работ —
в [`plan.md`](../specs/changes/frontend-agent-integration/plan.md), результаты
проверки — в
[`verification.md`](../specs/changes/frontend-agent-integration/verification.md).
