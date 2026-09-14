# Docker

Этот каталог содержит контейнерный запуск backend.

## Запуск

Из корня репозитория:

```sh
make run
```

По умолчанию API доступен на `http://localhost:8000`. Для локального изменения
настроек скопируйте `docker/.env.example` в `docker/.env`; этот файл не
отслеживается Git.

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
выполняется в фоне, а его результат в текущей версии доступен только в
in-memory истории и серверных логах.

## Состав

- `compose.yaml` — единственный сервис backend;
- `Dockerfile` — Python 3.12 образ с зависимостями из `backend/uv.lock`;
- `.env.example` — несекретные настройки порта и fake-агента.

Frontend в Compose не входит и запускается отдельно.

RAG остаётся будущим внутренним инструментом backend и пока не добавлен в
Compose.
