# Проверка: единый контейнерный запуск с Caddy и Nginx

## Результат

Изменение соответствует [spec.md](./spec.md). Локальный Compose стек собран и
проверен на отдельном тестовом проекте `smeshariki-compose-verify` с внешним
портом `18080`, чтобы не затрагивать пользовательские контейнеры. После проверки
его контейнеры и сеть удалены командой `docker compose ... down` без удаления
данных или образов. Браузер не запускался.

## Требования и критерии

| Требование | Подтверждение |
| --- | --- |
| REQ-001 | `docker compose ... up -d --build` собрал backend и frontend и запустил backend, frontend/Nginx и Caddy в одном проекте. `make run` использует тот же `docker/compose.yaml` с `up --build`; отдельный Vite-процесс не нужен. |
| REQ-002 | `docker build -f docker/frontend.Dockerfile .` успешно выполнил `npm ci` и Vite build; runtime слой — Nginx. HTTP-запросы к четырём ссылкам `/assets/...` из итогового HTML вернули `200`. |
| REQ-003 | Compose `ps` показал единственный опубликованный порт `127.0.0.1:18080->80/tcp` у Caddy; backend `8000/tcp` и frontend `80/tcp` остались внутренними. Значение `APP_PORT=18080` подтвердило переопределение default 8080. `GET /` вернул `200`, `POST /api/v1/dialogs` — backend `201` с `Location: /api/v1/dialogs/<uuid>`, то есть префикс сохранён. |
| REQ-004 | Через Caddy созданы диалог и SSE-подписка (`200 text/event-stream`, `ready`); сообщение получило `202`, затем поступили `message_start`, последовательные `message_delta` и `message_end`. `make test` прошёл, browser URL остались относительными. |
| REQ-005 | После остановки только backend `GET /` остался `200`, `POST /api/v1/dialogs` вернул `502`, а не HTML frontend. После запуска того же backend API снова вернул `201` без пересборки frontend или перезапуска Caddy. Healthchecks обоих upstream обеспечили начальный старт Caddy после готовности. |
| REQ-006 | Ревью Compose показало передачу LLM environment только backend. `.dockerignore` исключает `docker/.env`; локальный файл не попал в diff. Новые контейнерные файлы размещены в `docker/`. |
| REQ-007 | Обновлены `README.md`, `docker/README.md`, `frontend/README.md`, `docs/README.md`, `docs/dialogs.md`, `AGENTS.md` и описание `make run`; Vite dev-режим сохранён и его proxy smoke прошёл. Python-код продукта не изменён. |

## Команды

- `docker build -f docker/frontend.Dockerfile -t smeshariki-ai-frontend-verify .` — успешно.
- `docker compose --env-file docker/.env -f docker/compose.yaml config --quiet` — успешно.
- `APP_PORT=18080 docker compose -p smeshariki-compose-verify --env-file docker/.env -f docker/compose.yaml up -d --build` — успешно, три сервиса запущены.
- Локальные HTTP/SSE smoke-запросы к `http://127.0.0.1:18080` через Node `fetch` — успешно: HTML и assets `200`, создание `201`, SSE `ready`, отправка `202`, финал `message_end`.
- `docker compose -p smeshariki-compose-verify --env-file docker/.env -f docker/compose.yaml stop backend` / `start backend` — отказ `502` и восстановление `201` подтверждены.
- `UV_CACHE_DIR=/private/tmp/smeshariki-uv-cache make test` — 19 frontend Node-тестов и 132 backend Pytest, все прошли. Первый запуск без расширенного доступа завершился ошибкой sandbox `uv`; повтор с доступом прошёл.
- `npm --prefix frontend run build` — успешно.
- `npm --prefix frontend run test:proxy` — успешно после предоставления доступа к локальному порту; без доступа sandbox отклонил bind на `127.0.0.1`.
- `git diff --check` — успешно.
- `docker compose -p smeshariki-compose-verify --env-file docker/.env -f docker/compose.yaml down` — удалены только тестовые контейнеры и сеть.

## Ограничения

- Проверен локальный HTTP-вход. Публичный домен, TLS и сертификаты не входят в
  эту спецификацию.
- Сам `make run` не запускался поверх возможного пользовательского Compose
  проекта; проверен эквивалентный вызов того же файла с отдельным именем
  проекта и тестовым портом. Это сохранило пользовательское окружение.
- Внешний LLM вернул потоковый ответ во время smoke-проверки; его доступность
  зависит от пользовательской конфигурации и не гарантируется Compose.
