# Docker

Этот каталог содержит единый контейнерный запуск приложения: Caddy принимает
запросы с хоста, Nginx раздаёт собранный frontend, backend обслуживает API и
SSE, PostgreSQL хранит пользователей, Redis — blacklist access-токенов. Все
сервисы запускаются одним Docker Compose проектом с явным именем
`smeshariki-ai`, чтобы не пересекаться с другими проектами, чьи compose-файлы
тоже лежат в каталоге `docker/`.

## Запуск

Из корня репозитория:

```sh
make run
```

Перед первым запуском скопируйте `docker/.env.example` в `docker/.env`, выберите
поддерживаемую LiteLLM модель в `LLM_MODEL` и при необходимости задайте
`LLM_API_KEY` и `LLM_BASE_URL`. Также обязательны `AUTH_JWT_SECRET` (не короче
32 байт; в шаблоне он пустой, сгенерируйте его командой
`openssl rand -base64 48` — без него `make run` останавливается сообщением
`Set AUTH_JWT_SECRET in docker/.env`, а значения с префиксом `replace-with-`
backend отклоняет) и `POSTGRES_PASSWORD`. Локальный `docker/.env` не отслеживается Git;
реальные секреты не должны попадать в `.env.example`.

После запуска frontend доступен на `http://localhost:8090/`, demo-макет панели
администратора — на `http://localhost:8090/admin/`, страница входа и регистрации —
на `http://localhost:8090/login/`, API — на том же origin по
пути `/api/v1/...`. Значение `APP_PORT` в `docker/.env` меняет внешний
порт. Compose публикует только порт Caddy на `127.0.0.1`; backend и Nginx
доступны лишь внутри его сети. Локальный вход использует HTTP: публичный домен
и HTTPS этим изменением не настроены.

Лимиты попыток входа и регистрации (`AUTH_LOGIN_MAX_FAILURES`,
`AUTH_LOGIN_FAILURE_WINDOW_SECONDS`, `AUTH_LOGIN_MAX_PER_IP`,
`AUTH_LOGIN_PER_IP_WINDOW_SECONDS`, `AUTH_REGISTER_MAX_PER_IP`,
`AUTH_REGISTER_PER_IP_WINDOW_SECONDS`) имеют значения по умолчанию в
`.env.example` и описаны в [`docs/configuration.md`](../docs/configuration.md).
Для определения IP клиента сеть Compose использует подсеть `172.31.250.0/24`,
Caddy получает в ней фиксированный адрес `172.31.250.250`, а backend доверяет
`X-Forwarded-For` только от него (`FORWARDED_ALLOW_IPS`). Если подсеть
пересекается с вашей локальной сетью Docker, измените её и адрес в
`compose.yaml` согласованно. Без Docker Uvicorn по умолчанию доверяет только
`127.0.0.1`.

Backend использует LiteLLM Python SDK внутри своего процесса. `LLM_MODEL`
обязателен. Таймаут одного запроса задаётся `LLM_TIMEOUT_SECONDS` (по умолчанию
60 секунд), число повторов — `LLM_NUM_RETRIES` (по умолчанию 0), температура —
`LLM_TEMPERATURE` (`0…2`, по умолчанию `0.8`). `LLM_THINKING` включает скрытые
рассуждения DeepSeek; по умолчанию `false`. Для не-DeepSeek модели
`LLM_THINKING=true` отклоняется при старте. Отдельный LiteLLM Proxy не
запускается.

Локальная озвучка включается `SPEECH_ENABLED` (в шаблоне и Compose по
умолчанию `false`, пока модель не подготовлена; значение по умолчанию в
`SpeechConfig` — `true`) и использует Silero v5 на CPU. Голос задаётся `SPEECH_VOICE` (`baya` по
умолчанию), скорость — `SPEECH_SPEED`, одновременность — `SPEECH_MAX_CONCURRENCY`,
а путь к модели — `SPEECH_MODEL_PATH=/models/silero/v5_ru.pt`. Модель не
коммитится: скачайте её на хосте в `docker/models/silero/v5_ru.pt` скриптом
`SILERO_MODEL_SHA256=<sha256> docker/fetch-silero.sh docker/models/silero/v5_ru.pt`
и включите `SPEECH_ENABLED=true`. Compose монтирует `docker/models` в
контейнер read-only. Без модели оставьте `SPEECH_ENABLED=false`, иначе backend
остановится при старте.
MP3-файлы озвучки хранятся в Ceph RGW-совместимом сервисе `ceph-rgw`
(`quay.io/s3gw/s3gw`, файловый backend, внутренний порт `7480`, том
`ceph-data`). Backend обращается к нему по `CEPH_S3_ENDPOINT`; bucket
`CEPH_S3_BUCKET` создаётся идемпотентно. Секрет `CEPH_S3_SECRET_KEY`
передаётся только через `docker/.env`. Образ `ceph-rgw` собран под
`linux/amd64`; на Apple Silicon Docker использует эмуляцию.

`LOG_LEVEL` задаёт уровень журнала backend (`DEBUG`, `INFO`, `WARNING`,
`ERROR`), `LOG_FORMAT` выбирает читаемый формат `human` либо построчный `json`.
По умолчанию используются `INFO` и `human`. Логи доступны через
`docker compose -f docker/compose.yaml logs backend`; поля и границы метрик
описаны в [каталоге логирования](../docs/logging.md).

Перед стартом backend одноразовый сервис `migrate` (тот же образ) выполняет
`python -m smeshariki_ai.db.migrate`; backend запускается только после его
успешного завершения и готовности Redis. Применить миграции отдельно, без
запуска всего приложения, можно командой `make migrate`. Данные PostgreSQL хранятся в томе
`smeshariki-ai_postgres-data`; Redis работает без персистентности, так как
записи blacklist живут не дольше access-токена. Пароль PostgreSQL применяется
только при первой инициализации тома: после его смены удалите том командой
`docker compose -f docker/compose.yaml down -v` (данные будут потеряны).

Регистрация, вход и текущий пользователь:

```sh
curl -i http://localhost:8090/api/v1/users \
  -H 'Content-Type: application/json' -d '{"login":"krosh","password":"password123"}'
curl -i -c cookies.txt http://localhost:8090/api/v1/auth/login \
  -H 'Content-Type: application/json' -d '{"login":"krosh","password":"password123"}'
curl -i -b cookies.txt http://localhost:8090/api/v1/users/me
```

Ручки диалогов требуют ту же cookie: добавляйте `-b cookies.txt` к запросам
`/api/v1/dialogs/...`.

Создание администратора (миграции применяются автоматически, пароль
запрашивается дважды без отображения):

```sh
make create-admin LOGIN=sovunya
```

Полный контракт, включая `refresh` и `logout`, — в
[`docs/auth.md`](../docs/auth.md).

Создание диалога:

```sh
curl -i -X POST http://localhost:8090/api/v1/dialogs
```

Отправка сообщения, где `<dialog_id>` взят из первого ответа:

```sh
curl -i -X POST http://localhost:8090/api/v1/dialogs/<dialog_id>/messages \
  -H 'Content-Type: application/json' \
  -d '{"request":"Кто такой Крош?"}'
```

Ручка сообщения немедленно возвращает пустой `202 Accepted`. Agent loop
выполняется в фоне, а его потоковые события доступны через
`GET /api/v1/dialogs/<dialog_id>/events`. Caddy сохраняет префикс `/api` и
направляет эти запросы напрямую в backend; Nginx не проксирует API.
Подробности frontend — в [`frontend/README.md`](../frontend/README.md).

## Состав

- `compose.yaml` — сервисы backend, migrate, PostgreSQL, Redis, Ceph RGW,
  frontend/Nginx и Caddy;
- `Dockerfile` — Python 3.12 образ backend с зависимостями из `backend/uv.lock`;
- `frontend.Dockerfile` — Node.js 22 build frontend и runtime Nginx;
- `nginx.conf` — конфиг Nginx: относительные редиректы на каталог
  (`absolute_redirect off`, `/login` → `/login/` без потери порта Caddy),
  `Cache-Control: no-cache` для HTML и `immutable` для хешированных
  `/assets/`; несуществующие пути — `404` без SPA fallback
  ([spec](../specs/changes/frontend-nginx-config/spec.md),
  [verification](../specs/changes/frontend-nginx-config/verification.md));
- `Caddyfile` — маршруты `/api` к backend и остальных запросов к Nginx;
- `.env.example` — несекретный шаблон порта, агента, LiteLLM-провайдера, логов,
  аутентификации, PostgreSQL, локальной озвучки Silero и Ceph.
- `fetch-silero.sh` — загрузка и проверка SHA-256 модели Silero v5.
- `compose.test.yaml` и `test-integration.sh` — временные PostgreSQL и Redis
  для `make test-integration`.

`make frontend` по-прежнему запускает отдельный Vite dev server при разработке;
для основного запуска он не нужен.

## Интеграционные тесты

`make test` не требует Docker и пропускает тесты PostgreSQL и Redis. Полный
backend-набор на настоящих хранилищах запускает команда:

```sh
make test-integration
make test-integration PYTEST_ARGS="backend/tests/integration/rag -x"
```

Команда поднимает отдельный Compose-проект `smeshariki-ai-test` из
`compose.test.yaml` (`pgvector/pgvector:pg17` и `redis:7-alpine`), ждёт
healthcheck и запускает pytest на хосте через `uv` с `TEST_DATABASE_URL` и
`TEST_REDIS_URL`. Проект не читает `docker/.env`, не использует тома и сеть
основного стека и может работать рядом с `make run`. Порты выбираются Docker
динамически и публикуются только на `127.0.0.1`; данные хранятся в `tmpfs`
(PostgreSQL — до 512 МБ), поэтому каждый запуск начинается с пустой БД и не
пишет на диск. Учётные данные фиксированные тестовые (`test`/`test`).

`PYTEST_ARGS` заменяет аргументы pytest (по умолчанию `backend`). Код
возврата — код pytest. Контейнеры, сеть и тома проекта удаляются после
успеха, падения, ошибки запуска и `Ctrl+C`, а остатки прерванного запуска —
перед стартом. Без Docker команда завершается с ошибкой и pytest не
запускает. Подробности — в
[`spec.md`](../specs/changes/postgres-test-env/spec.md).

RAG является внутренним инструментом backend; его команды `check`, `schema` и
`load` выполняются через `uv` или Compose, а `export`, `delete` и `restore` —
через Compose-сервис `migrate`. Отдельного RAG-сервиса в Compose нет.

Контракт единого запуска описан в
[`spec.md`](../specs/changes/compose-caddy-nginx-stack/spec.md), порядок
реализации — в [`plan.md`](../specs/changes/compose-caddy-nginx-stack/plan.md),
результаты проверки — в
[`verification.md`](../specs/changes/compose-caddy-nginx-stack/verification.md).
