# Docker

Этот каталог содержит единый контейнерный запуск приложения: Caddy принимает
запросы с хоста, Nginx раздаёт собранный frontend, backend обслуживает API и
SSE. Все три сервиса запускаются одним Docker Compose проектом.

## Запуск

Из корня репозитория:

```sh
make run
```

Перед первым запуском скопируйте `docker/.env.example` в `docker/.env`, выберите
поддерживаемую LiteLLM модель в `LLM_MODEL` и при необходимости задайте
`LLM_API_KEY` и `LLM_BASE_URL`. Локальный `docker/.env` не отслеживается Git;
реальные секреты не должны попадать в `.env.example`.

После запуска frontend доступен на `http://localhost:8080/`, API — на том же
origin по пути `/api/v1/...`. Значение `APP_PORT` в `docker/.env` меняет внешний
порт. Compose публикует только порт Caddy на `127.0.0.1`; backend и Nginx
доступны лишь внутри его сети. Локальный вход использует HTTP: публичный домен
и HTTPS этим изменением не настроены.

Backend использует LiteLLM Python SDK внутри своего процесса. `LLM_MODEL`
обязателен. Таймаут одного запроса задаётся `LLM_TIMEOUT_SECONDS` (по умолчанию
60 секунд), а число повторов — `LLM_NUM_RETRIES` (по умолчанию 0). Отдельный
LiteLLM Proxy не запускается.

Создание диалога:

```sh
curl -i -X POST http://localhost:8080/api/v1/dialogs
```

Отправка сообщения, где `<dialog_id>` взят из первого ответа:

```sh
curl -i -X POST http://localhost:8080/api/v1/dialogs/<dialog_id>/messages \
  -H 'Content-Type: application/json' \
  -d '{"request":"Кто такой Крош?"}'
```

Ручка сообщения немедленно возвращает пустой `202 Accepted`. Agent loop
выполняется в фоне, а его потоковые события доступны через
`GET /api/v1/dialogs/<dialog_id>/events`. Caddy сохраняет префикс `/api` и
направляет эти запросы напрямую в backend; Nginx не проксирует API.
Подробности frontend — в [`frontend/README.md`](../frontend/README.md).

## Состав

- `compose.yaml` — сервисы backend, frontend/Nginx и Caddy;
- `Dockerfile` — Python 3.12 образ backend с зависимостями из `backend/uv.lock`;
- `frontend.Dockerfile` — Node.js 22 build frontend и runtime Nginx;
- `Caddyfile` — маршруты `/api` к backend и остальных запросов к Nginx;
- `.env.example` — несекретный шаблон порта, агента и LiteLLM-провайдера.

`make frontend` по-прежнему запускает отдельный Vite dev server при разработке;
для основного запуска он не нужен.

RAG остаётся будущим внутренним инструментом backend и пока не добавлен в
Compose.

Контракт единого запуска описан в
[`spec.md`](../specs/changes/compose-caddy-nginx-stack/spec.md), порядок
реализации — в [`plan.md`](../specs/changes/compose-caddy-nginx-stack/plan.md),
результаты проверки — в
[`verification.md`](../specs/changes/compose-caddy-nginx-stack/verification.md).
