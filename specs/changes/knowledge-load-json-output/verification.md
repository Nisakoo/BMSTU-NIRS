# Verification: чистый stdout у `make knowledge-load`

Исторический оригинал: `git show 5af56b5:specs/changes/knowledge-load-json-output/verification.md`.

## Результат

- Изменение `knowledge-load-json-output` соответствует согласованной спецификации. До исправления stdout цели с `FORMAT=json` начинался с лога сборки образа и не разбирался как JSON; после исправления stdout содержит только отчёт `load`. Заодно выполнены проверки, которые не удалось провести в `knowledge-postgres-store` и `knowledge-hardening` из-за сбоя Docker: полный `make knowledge-load` и полный backend-набор на PostgreSQL 17 с Redis.
- Проверка шла в изолированном Compose-проекте `smeshariki-rag-verify` с временным env-файлом вне репозитория и синтетическим пакетом из примеров `docs/knowledge.md`, дополненным континуумом `movies` и персонажем `krosh`.
- backend: 585 passed, 64 skipped (PostgreSQL- и Redis-тесты без переменных)
- 649 passed, 0 skipped; postgres:17-alpine (PostgreSQL 17.10), redis:7-alpine
- После исправления образ собирался с удалённым образом проекта, но слои брались из кэша BuildKit. Сборка полностью без кэша наблюдалась до исправления и печатала весь лог в stdout. Сброс кэша требует глобального `docker builder prune`, затрагивающего другие проекты, и не выполнялся. Перенаправление переносит в stderr весь stdout `migrate` независимо от кэша.
- Код возврата цели при ошибке — собственный код `make` `2`, а не код `load`; это прежнее поведение, описанное в `docs/rag.md` для `knowledge-check`.
- Без доступа LiteLLM к сети импорт модуля агента по-прежнему добавляет задержку и предупреждение в stderr; stdout это не затрагивает.
