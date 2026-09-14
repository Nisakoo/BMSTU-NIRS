# Verification: диалоги агента и фоновый HTTP-запуск

Дата проверки: 13 сентября 2026 года.

## Результат

Изменение `agent-dialog-api` соответствует одобренной спецификации. Все
критерии приёмки подтверждены поведенческими тестами, ревью зависимостей и
реальным HTTP smoke-тестом backend, запущенного командой `make run` через Docker
Compose.

## Проверка требований

| Требования | Подтверждение | Результат |
| --- | --- | --- |
| REQ-001–REQ-002 | Unit-тесты ABC `HistoryStore`, UUIDv4, пустой и изолированной истории, неизменяемого снимка, атомарного append и неизвестного диалога | Пройдено |
| REQ-003–REQ-007 | Unit-тесты application-сервиса: внедрение Agent/store, ранний возврат submit, фоновый запуск, порядок user/assistant и отсутствие внутренних сообщений Agent в истории | Пройдено |
| REQ-008–REQ-010 | Unit-тесты rollback истории при ошибке, последовательной очереди одного диалога, независимых диалогов, отслеживания и отмены задач при shutdown | Пройдено |
| REQ-011 | Тесты bootstrap: config, `FakeLLMProvider`, пустой `ToolRegistry`, Agent, store и service собираются вне HTTP-сервиса | Пройдено |
| REQ-012 | `caplog`-тесты lifecycle и ошибок; контейнерный smoke подтвердил видимые logfmt-события с `dialog_id` без пользовательского payload | Пройдено |
| REQ-013–REQ-015 | HTTP-тесты и container smoke: `201`, `Location`, UUID JSON и немедленный пустой `202` до завершения агента | Пройдено |
| REQ-016–REQ-017 | HTTP-тесты отдельных ответов `404`, `422` и безопасного `503`; при отклонении агент не запускается | Пройдено |
| REQ-018–REQ-019 | HTTP-тест cookie и ревью приложения: dialog определяется URL, `Set-Cookie`, CORS middleware, SSE и streaming response отсутствуют | Пройдено |
| REQ-020 | `docker compose config`, production build, `make run`, HTTP smoke и graceful shutdown; Compose содержит только backend | Пройдено |
| REQ-021 | `make test`: 54 теста без сети, реального LLM, Qdrant и RAG | Пройдено |
| REQ-022 | Ревью актуализированных `AGENTS.md`, корневого и backend/Docker README | Пройдено |

## Выполненные команды

```text
make lint
All checks passed; 28 files already formatted

make test
54 passed in 0.35s

uv lock --project backend --check
Resolved 25 packages in 4ms

uv tree --project backend
runtime: FastAPI 0.141.1, Pydantic 2.13.5, Uvicorn 0.52.4
dev: HTTPX 0.28.1, Pytest 9.1.1, pytest-asyncio 1.4.0, Ruff 0.16.7

docker compose -f docker/compose.yaml config --services
backend

make run
image built; backend started on 0.0.0.0:8000

POST /api/v1/dialogs
201 Created + Location + UUIDv4 JSON

POST /api/v1/dialogs/{dialog_id}/messages
202 Accepted + Content-Length: 0

docker run --rm docker-backend python -c "..."
production image dependencies: ok
```

При контейнерном smoke в серверном журнале подтверждены события:

```text
dialog.created dialog_id=<uuid>
dialog.request.accepted dialog_id=<uuid>
dialog.run.started dialog_id=<uuid>
agent.run.started history_size=0 max_iterations=4
agent.iteration.started iteration=1
agent.llm.completed iteration=1 result_type=final
agent.run.completed iterations=1
dialog.run.completed dialog_id=<uuid>
dialog.history.persisted dialog_id=<uuid>
```

Контейнер был штатно остановлен через SIGINT; FastAPI lifespan завершился без
необработанных исключений. Одноразовая проверка production-образа подтвердила,
что Pytest, HTTPX и Ruff в него не установлены.

## Критерии приёмки

- Новый UUIDv4-диалог с пустой историей создаётся через HTTP — подтверждено.
- Сообщение ставится в очередь и немедленно получает пустой 202 — подтверждено.
- Результат и внутренний прогресс агента не попадают в HTTP-ответ —
  подтверждено.
- Fake-провайдер сохраняет пустой финальный ответ в историю — подтверждено.
- Очередь последовательна внутри диалога и независима между диалогами —
  подтверждено.
- Ответы 404/422 и обязательный UUID в URL работают без cookie — подтверждено.
- Фоновая ошибка не меняет историю и безопасно журналируется — подтверждено.
- Фоновые задачи отслеживаются и корректно отменяются при shutdown —
  подтверждено.
- Agent loop наблюдаем в реальном серверном журнале без payload — подтверждено.
- CORS и потоковые ответы отсутствуют — подтверждено.
- `make run` запускает Compose только с backend — подтверждено.
- `make test` проходит без внешней инфраструктуры — подтверждено.
- Архитектурная документация соответствует реализации — подтверждено.

Повторное архитектурное ревью подтвердило, что `AgentService` и его ошибки
находятся в `smeshariki_ai.application`, а пакет `smeshariki_ai.dialogs`
содержит только контракт и реализацию истории вместе с ошибками диалогов.
После переноса `make lint` и все 54 продуктовых теста повторно прошли успешно;
runtime-проверка подтвердила отсутствие экспорта `AgentService` из `dialogs`.
Production-образ был повторно собран, и та же граница импортов подтверждена
внутри одноразового контейнера.

## Известные ограничения

- История и очередь существуют только в памяти одного процесса и теряются при
  рестарте.
- API пока не предоставляет чтение истории или результата фонового запуска.
- Используется `FakeLLMProvider`; CORS, SSE, RAG, внешний broker, база данных и
  аутентификация не входят в эту версию.
- `dialog_id` является идентификатором ресурса, но не механизмом авторизации.
