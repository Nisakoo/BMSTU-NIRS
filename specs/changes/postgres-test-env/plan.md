# План: тестовое окружение PostgreSQL и Redis одной командой

## Основание

План реализует согласованную спецификацию
`specs/changes/postgres-test-env/spec.md` в ветке `feat/postgres-test-env`.

## Решения и зависимости

- `docker/compose.test.yaml` задаёт имя проекта `smeshariki-ai-test` полем
  `name`, а скрипт дополнительно передаёт `-p`, чтобы уборка не зависела от
  содержимого файла.
- Порты публикуются как `127.0.0.1::5432` и `127.0.0.1::6379`; скрипт
  получает их через `docker compose port`.
- Данные PostgreSQL (`/var/lib/postgresql/data`) и Redis (`/data`) находятся
  в `tmpfs`, поэтому анонимные тома из `VOLUME` образов не создаются.
  PostgreSQL запускается с `fsync=off`: данные одноразовые.
- Скрипт — POSIX `sh` без `set -e`: код pytest сохраняется явно, уборка —
  в `trap ... EXIT`; `INT` и `TERM` переводятся в выход с кодами `130` и `143`.
- `PYTEST_ARGS` приходит в скрипт через environment (Make экспортирует
  переменные командной строки) и разбивается на слова без glob-подстановки.
- Сообщения скрипта — на английском, как у остальных целей `Makefile`.
- Ресурсы компьютера: перед и после каждого прогона проверяются `df -h`
  (C: и диск WSL), `free -h` и `docker system df`; образы не собираются и не
  скачиваются (`postgres:17-alpine` и `redis:7-alpine` уже есть).

## Порядок реализации

1. Compose-файл и скрипт запуска.
2. Цель `Makefile` и документация.
3. Verify.

## Задача 1. Compose-файл и скрипт

**Связанные требования:** REQ-001–REQ-009.

**Критерии приёмки:** скрипт поднимает окружение, запускает pytest с
`TEST_DATABASE_URL` и `TEST_REDIS_URL`, возвращает код pytest, убирает
ресурсы при любом исходе, удаляет остатки прошлого запуска и сообщает о
недоступном Docker.

**Зависимости:** нет.

**Файлы:** `docker/compose.test.yaml`, `docker/test-integration.sh`.

**Проверка:** `sh docker/test-integration.sh` с подмножеством
`backend/tests/integration/rag`; `docker compose ls`, `docker ps -a`,
`docker volume ls` после запуска.

## Задача 2. Цель `Makefile` и документация

**Связанные требования:** REQ-005, REQ-010.

**Критерии приёмки:** `make test-integration [PYTEST_ARGS=...]` вызывает
скрипт; `make help`, `docker/README.md`, `docs/README.md` и `AGENTS.md`
описывают команду; diff общих файлов только аддитивный.

**Зависимости:** задача 1.

**Файлы:** `Makefile`, `docker/README.md`, `docs/README.md`, `AGENTS.md`.

**Проверка:** `make help`; `git diff --stat` и `git diff` общих файлов
без удалённых строк; ревью текста.

## Задача 3. Verify

**Связанные требования:** все.

**Критерии приёмки:** все сценарии таблицы «Тестирование» спецификации
выполнены; `verification.md` записан; ресурсов проекта `smeshariki-ai-test`
не осталось.

**Зависимости:** задачи 1–2.

**Файлы:** `specs/changes/postgres-test-env/verification.md`.

**Проверка:** `make test-integration`; сценарии с `PYTEST_ARGS`, падением,
`Ctrl+C`, остатками запуска, занятым портом и недоступным `DOCKER_HOST`;
`make lint`; `make test`.
