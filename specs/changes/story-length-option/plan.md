# План: выбор длины истории

Спецификация: [spec.md](./spec.md).

## Порядок

Сначала backend по TDD: доменная модель и runtime агента, затем HTTP-валидация.
Потом клиент API и UI. Ручная проверка с реальной моделью — последней.

## Задача 1. Указание длины в runtime агента

**Требования:** REQ-007, REQ-008, REQ-009.

**Решение:** `UserRequest` получает `reading_minutes: Literal[2, 5, 10] | None
= None`. `Agent.run` при заданной длине вставляет второе системное сообщение
сразу после основного промпта; число слов — `minutes × 150`. `AgentService`
по-прежнему сохраняет `Message(USER, request.content)`. Событие
`agent.run.started` получает поле `reading_minutes`.

**Критерии приёмки:** контекст, переданный `FakeLLMProvider`, содержит
сообщение «Объём ответа: история примерно на N минут чтения — около W слов.»
для 2/5/10 и не содержит его без длины; история после запуска содержит только
текст запроса.

**Файлы:** `backend/src/smeshariki_ai/agent/models.py`,
`backend/src/smeshariki_ai/agent/runtime.py`,
`backend/tests/unit/agent/test_runtime.py`,
`backend/tests/unit/application/test_agent_service.py`.

**Проверка:** `uv run --project backend --locked pytest backend/tests/unit`.

## Задача 2. HTTP-контракт

**Требования:** REQ-006.

**Критерии приёмки:** `202` без поля и с 2/5/10; `422` для `0`, `3`, `7`,
`"5"`, `5.5`, `null`; при `422` агент не запускается; `reading_minutes`
доходит до агента.

**Файлы:** `backend/src/smeshariki_ai/api/schemas.py`,
`backend/src/smeshariki_ai/api/app.py`,
`backend/tests/integration/api/test_dialogs.py`.

**Проверка:** `uv run --project backend --locked pytest backend/tests/integration/api`;
`make lint`.

## Задача 3. Клиент API и UI

**Требования:** REQ-001…REQ-005.

**Решение:** `AgentApi.submitMessage(dialogId, request, { readingMinutes })`
добавляет поле только при заданной длине. В композере — нативный `<select
id="saiLength">` с подписью для экранных читалок, стилизованный под чипы.
`script.js` читает значение при отправке и блокирует список в `updateForm`.

**Критерии приёмки:** Node-тесты тела запроса и UI (передача длины, сохранение
после «+ Новая история», блокировка); скриншоты `1440x900`, `320x640` без
горизонтальной прокрутки.

**Файлы:** `frontend/src/agent-api.js`, `frontend/src/index.html`,
`frontend/src/styles.css`, `frontend/src/script.js`,
`frontend/tests/agent-api.test.js`, `frontend/tests/ui.test.js`.

**Проверка:** `npm --prefix frontend test`; пересборка frontend; замер
headless Chrome.

## Задача 4. Документация и ручная проверка

**Файлы:** `docs/agent.md`, `docs/dialogs.md`, `frontend/README.md`,
`AGENTS.md`.

**Проверка:** ревью; `make test`; в `make run` запросы с «~2 мин» и «~10 мин»
дают ответы заметно разного объёма.
