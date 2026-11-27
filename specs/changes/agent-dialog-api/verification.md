# Verification: диалоги агента и фоновый HTTP-запуск

Дата проверки: 13 сентября 2026 года. Результат: требования выполнены.
Полный исходный отчёт: `git show 9b31004:specs/changes/agent-dialog-api/verification.md`.

| Требования | Подтверждение |
| --- | --- |
| REQ-001–002 | Unit: UUID, пустая и изолированная история, атомарность, неизвестный диалог. |
| REQ-003–010 | Unit: фоновый запуск, порядок сообщений, rollback, очереди диалогов и shutdown. |
| REQ-011–012 | Bootstrap и безопасные lifecycle-логи проверены тестами и контейнерным smoke. |
| REQ-013–019 | HTTP-тесты и smoke: 201, Location, UUID, пустой 202, 404/422/503 и выбор диалога через URL. |
| REQ-020 | Compose config, production build, `make run`, HTTP smoke и graceful shutdown. |
| REQ-021–022 | `make test`, ревью зависимостей и документации. |

`make lint` прошёл; `make test` — 54 passed; `uv lock --check` и `uv tree` выполнены.
Production-образ проверен без Pytest, HTTPX и Ruff. Smoke подтвердил безопасные
логи и штатное завершение lifespan. После переноса `AgentService` в application
`make lint`, 54 теста и проверка импортов в пересобранном образе прошли повторно.

На момент проверки история и очередь были in-memory и терялись при рестарте.
Чтение истории, SSE, RAG, внешний broker, БД и аутентификация не входили в эту
версию; `dialog_id` не был механизмом авторизации. Позднейшие изменения описаны
в [каталоге архитектуры](../../../docs/README.md).
