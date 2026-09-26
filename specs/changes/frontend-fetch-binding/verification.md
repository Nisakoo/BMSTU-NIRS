# Проверка: контекст browser fetch в frontend API-клиенте

## Результат

Проверка завершена 23 сентября 2026 года. Причина отсутствия HTTP-запросов
из открытой страницы устранена: сохранённый browser `fetch` больше не
вызывается с объектом `AgentApi` в качестве `this`. Пользователь подтвердил,
что после обновления страницы статус стал «готов к идеям», а отправленное
сообщение получило ответ агента. Браузер со стороны разработчика не
запускался по указанию пользователя.

## Требования и доказательства

| Требования | Доказательство | Результат |
| --- | --- | --- |
| REQ-001, REQ-003 | Receiver-sensitive fake `fetch` в `frontend/tests/agent-api.test.js` | До исправления оба теста падали с `create_failed` и `submit_failed`; после привязки `fetch` к `globalThis` проходят |
| REQ-002 | Существующие тесты API-контракта, UI-состояний и подтверждение пользователя | URL, JSON, статусы и SSE не менялись; создание диалога и отправка сообщения работают из открытой страницы |
| REQ-004 | `test:proxy`, ревью diff | Vite proxy, backend, Docker Compose и browser origin не изменены |

## Команды и результаты

```sh
UV_CACHE_DIR=/private/tmp/smeshariki-uv-cache UV_NO_SYNC=1 make test
npm --prefix frontend run build
npm --prefix frontend run test:proxy
UV_CACHE_DIR=/private/tmp/smeshariki-uv-cache UV_NO_SYNC=1 make lint
git diff --check
```

- `make test`: 19 frontend Node-тестов и 132 backend Pytest-теста прошли.
- Vite build, proxy smoke, Ruff и `git diff --check` прошли.
- Работающий Vite отдаёт JS с `fetchImpl.bind(globalThis)`.
- После обновления страницы пользователь подтвердил `ready` и ответ агента;
  backend-логи подтвердили `POST /api/v1/dialogs` (`201`) и подключение SSE
  (`200`) из вкладки.

`UV_CACHE_DIR` и `UV_NO_SYNC` использованы только для доступа к существующему
Python-окружению в текущей песочнице.

## Ограничения

- Браузерная отрисовка не проверялась агентом; результат работы страницы
  подтверждён пользователем.
- Поставщик LLM, in-memory история и отсутствие SSE replay не менялись.
