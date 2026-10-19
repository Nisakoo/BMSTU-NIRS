# Verification: чистый stdout у `make knowledge-load`

Дата проверки: 19 октября 2026 года.

## Результат

Изменение `knowledge-load-json-output` соответствует согласованной
спецификации. До исправления stdout цели с `FORMAT=json` начинался с лога
сборки образа и не разбирался как JSON; после исправления stdout содержит
только отчёт `load`. Заодно выполнены проверки, которые не удалось провести в
`knowledge-postgres-store` и `knowledge-hardening` из-за сбоя Docker: полный
`make knowledge-load` и полный backend-набор на PostgreSQL 17 с Redis.

Проверка шла в изолированном Compose-проекте `smeshariki-rag-verify` с
временным env-файлом вне репозитория и синтетическим пакетом из примеров
`docs/knowledge.md`, дополненным континуумом `movies` и персонажем `krosh`.

## Проверка требований

| Требования | Подтверждение | Результат |
| --- | --- | --- |
| REQ-001, REQ-002 | До исправления: `make knowledge-load … FORMAT=json > out` — 106 строк, `json.load` падает на `#1 [internal] load local bake definitions`. После: образ проекта удалён, сборка в stderr, stdout — JSON с `"loaded": true`; повторная загрузка — JSON | Пройдено |
| REQ-002 | Отменённая загрузка (эпизод ссылается на персонажа, которого нет в БД): stdout — JSON с `"loaded": false`, код `2` | Пройдено |
| REQ-003 | Окружение без `LLM_MODEL`: `migrate` падает, `load` не запускается, stdout пуст (0 байт), причина в stderr, код `2`. Текстовый отчёт прежний. Подсказки без `DIR` и с несуществующим каталогом прежние, код `2` | Пройдено |
| REQ-004 | Ревью строки `make knowledge-load` в `docs/rag.md`; `git diff -- Makefile` — одна строка цели `knowledge-load` | Пройдено |

## Выполненные команды

```text
COMPOSE_PROJECT_NAME=smeshariki-rag-verify \
  make knowledge-load DIR=<пакет> ENV_FILE=<временный env> [FORMAT=json]
первая загрузка — 8 сущностей добавлено; повторные — все без изменений;
stdout с FORMAT=json разбирается json.load

make lint
All checks passed!; 129 files already formatted

make test
frontend: pass 103, fail 0
backend: 585 passed, 64 skipped (PostgreSQL- и Redis-тесты без переменных)

TEST_DATABASE_URL=… TEST_REDIS_URL=… uv run --project backend --locked pytest backend
649 passed, 0 skipped; postgres:17-alpine (PostgreSQL 17.10), redis:7-alpine
```

## Ограничения проверки

- После исправления образ собирался с удалённым образом проекта, но слои
  брались из кэша BuildKit. Сборка полностью без кэша наблюдалась до
  исправления и печатала весь лог в stdout. Сброс кэша требует глобального
  `docker builder prune`, затрагивающего другие проекты, и не выполнялся.
  Перенаправление переносит в stderr весь stdout `migrate` независимо от кэша.
- Код возврата цели при ошибке — собственный код `make` `2`, а не код `load`;
  это прежнее поведение, описанное в `docs/rag.md` для `knowledge-check`.
- Без доступа LiteLLM к сети импорт модуля агента по-прежнему добавляет
  задержку и предупреждение в stderr; stdout это не затрагивает.
