# Docker

Этот каталог содержит контейнерный запуск backend.

## Запуск

Из корня репозитория:

```sh
make run
```

По умолчанию API доступен на `http://localhost:8000`. Перед первым запуском
скопируйте `docker/.env.example` в `docker/.env`, выберите поддерживаемую LiteLLM
модель в `LLM_MODEL` и при необходимости задайте `LLM_API_KEY` и
`LLM_BASE_URL`. Локальный `docker/.env` не отслеживается Git; реальные секреты
не должны попадать в `.env.example`.

Backend использует LiteLLM Python SDK внутри своего процесса. `LLM_MODEL`
обязателен. Таймаут одного запроса задаётся `LLM_TIMEOUT_SECONDS` (по умолчанию
60 секунд), а число повторов — `LLM_NUM_RETRIES` (по умолчанию 0). Отдельный
LiteLLM Proxy не запускается.

Создание диалога:

```sh
curl -i -X POST http://localhost:8000/api/v1/dialogs
```

Отправка сообщения, где `<dialog_id>` взят из первого ответа:

```sh
curl -i -X POST http://localhost:8000/api/v1/dialogs/<dialog_id>/messages \
  -H 'Content-Type: application/json' \
  -d '{"request":"Кто такой Крош?"}'
```

Ручка сообщения немедленно возвращает пустой `202 Accepted`. Agent loop
выполняется в фоне, а его потоковые события доступны через
`GET /api/v1/dialogs/<dialog_id>/events`. Основной frontend подключается к этим
ручкам через локальный Vite proxy; подробности запуска находятся в
[`frontend/README.md`](../frontend/README.md).

## Состав

- `compose.yaml` — единственный сервис backend;
- `Dockerfile` — Python 3.12 образ с зависимостями из `backend/uv.lock`;
- `.env.example` — несекретный шаблон порта, агента и LiteLLM-провайдера.

Frontend в Compose не входит и запускается отдельно.

RAG остаётся будущим внутренним инструментом backend и пока не добавлен в
Compose.
