# Verification: тестовое окружение PostgreSQL и Redis одной командой

Дата проверки: 26 октября 2026 года.

## Результат

Изменение `postgres-test-env` соответствует согласованной спецификации.
`make test-integration` поднимает PostgreSQL 17.10 (`postgres:17-alpine`) и
Redis 7.4.9 (`redis:7-alpine`) в отдельном Compose-проекте
`smeshariki-ai-test`, прогоняет полный backend-набор без пропусков и убирает
ресурсы проекта при любом исходе. Образы не собирались и не скачивались.

При проверке REQ-006 уточнён в спецификации: GNU Make сводит ненулевой код
рецепта к `2`, поэтому точный код pytest возвращает скрипт, а цель Make —
`0` или ненулевой код с исходным значением в сообщении `Error <код>`.

## Проверка требований

| Требования | Подтверждение | Результат |
| --- | --- | --- |
| REQ-001, REQ-006 | `make test-integration`: 649 passed, 0 skipped, код `0`, 6 минут; число тестов совпадает с ручным прогоном из `knowledge-load-json-output` | Пройдено |
| REQ-002 | `docker compose ls` во время прогона: `smeshariki-ai-test` и параллельно работающий `data-migration-backend`; ревью: файл не ссылается на `docker/.env`, тома и сеть основного проекта | Пройдено |
| REQ-003 | Прогон при занятом `127.0.0.1:5432` (тестовый слушатель): PostgreSQL получил порт `127.0.0.1:42120`, тесты прошли | Пройдено |
| REQ-004 | Ревью `compose.test.yaml`: `tmpfs` 512 МБ для PostgreSQL и 16 МБ для Redis, тестовые учётные данные; после запусков томов проекта нет; повторные прогоны проходят миграции на пустой БД | Пройдено |
| REQ-005 | `make test-integration PYTEST_ARGS="backend/tests/integration/rag -x -q"` — 47 passed; `-k no_such_test_xyz` даёт код pytest `5` | Пройдено |
| REQ-006, REQ-007 | `-k` без тестов: скрипт — код `5`, make — `2`; `SIGINT` группе процессов make во время pytest: `Error 130`; после каждого запуска контейнеров, томов и сетей с меткой проекта — 0 | Пройдено |
| REQ-008 | После ручного `docker compose -p smeshariki-ai-test up -d` (2 контейнера, сеть) запуск подмножества `cache` — 9 passed, остатков 0 | Пройдено |
| REQ-009 | `DOCKER_HOST=unix:///nonexistent.sock make test-integration`: `Error: Docker is not available. Start Docker and retry.` в stderr, pytest не запускался, код `2` | Пройдено |
| REQ-010 | `make help` выводит команду; `git diff --numstat`: `Makefile` +6, `docker/README.md` +28, `docs/README.md` +1, `AGENTS.md` +2, удалённых строк нет; правка `AGENTS.md` согласована | Пройдено |

## Выполненные команды

```text
make test-integration
649 passed in 360.23s

make lint
All checks passed!; 129 files already formatted

make test
frontend: pass 103, fail 0
backend: 585 passed, 64 skipped (PostgreSQL- и Redis-тесты без переменных)
```

## Ресурсы компьютера

Во время полного прогона свободное место на C: не изменилось (63 ГБ),
доступная память не опускалась ниже 2,25 ГБ из 7,4 ГБ. Данные тестовых
хранилищ находятся в памяти (`tmpfs`) и на диск не пишутся.

## Ограничения

- Полный прогон длится около 6 минут из-за тестов других модулей, которые
  проверяют недоступность через `127.0.0.1:1`: в WSL с
  `networkingMode=mirrored` подключение ждёт таймаута. Исправление — в тестах
  владельцев модулей, вне этого изменения.
- Прерывание проверено сигналом `SIGINT` всей группе процессов `make`, как
  при `Ctrl+C` в терминале.
