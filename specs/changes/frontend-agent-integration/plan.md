# План: интеграция frontend с агентом через Vite proxy и SSE

## Основание

План реализует согласованную спецификацию
`specs/changes/frontend-agent-integration/spec.md`. Действующие dialog API и
SSE schema не меняются; Vite обеспечивает same-origin proxy для отдельно
запущенного frontend.

## Зависимости и порядок

1. Сначала вводится воспроизводимый Vite/npm-контур и стандартные команды, так
   как все следующие runtime-проверки зависят от proxy и сборки.
2. Затем сетевой контракт выделяется в независимый ES-модуль и покрывается
   Node-тестами до подключения DOM.
3. После зелёных сетевых тестов текущий UI переводится с демонстрационного
   ответа на реальное состояние dialog/SSE.
4. Документация обновляется после стабилизации команд и поведения.
5. В конце выполняются сборка, полный test/lint, Node-тесты UI-состояний и
   локальная HTTP/SSE-проверка Vite proxy без запуска браузера.

Рискованная граница — поток SSE через dev proxy. Она проверяется локальными
HTTP-запросами к Vite с несколькими delta и fake backend. UI-порядок и
блокировка формы проверяются отдельно в Node с fake DOM и EventSource.

## Задача 1. Добавить Vite/npm-контур

**Связанные требования:** REQ-001–REQ-003, REQ-016.

**Критерии приёмки:** Vite использует `frontend/src/` как root, проксирует
`/api` на default или `BACKEND_URL`, frontend запускается отдельной make-
командой, build output и зависимости игнорируются Git.

**Зависимости:** нет.

**Файлы:**

- `frontend/package.json`;
- `frontend/package-lock.json`;
- `frontend/vite.config.js`;
- `.gitignore`;
- `Makefile`.

**Действия:**

1. Добавить ESM package с командами `dev`, `build` и `test`.
2. Установить поддерживаемую стабильную Vite-версию через npm и зафиксировать
   lock-файл.
3. Настроить `root`, strict dev port и proxy `/api` с `changeOrigin`.
4. Добавить `make frontend`, frontend Node-тесты в `make test` и игнорирование
   `node_modules/`/`dist/`.

**Проверка:**

```sh
npm --prefix frontend test
npm --prefix frontend run build
git diff --check
```

## Задача 2. Реализовать и протестировать сетевой контракт

**Связанные требования:** REQ-004, REQ-006–REQ-009, REQ-012, REQ-014–REQ-015.

**Критерии приёмки:** ES-модуль формирует точные API-запросы, подключает
именованные SSE-события, безопасно разбирает JSON и закрывает EventSource;
Node-тесты проходят без сети.

**Зависимости:** задача 1.

**Файлы:**

- `frontend/src/agent-api.js`;
- `frontend/tests/agent-api.test.js`.

**RED:**

Добавить падающие тесты создания диалога, отправки сообщения, SSE dispatch,
invalid JSON и close.

**GREEN:**

Реализовать минимальный `AgentApi` с injected `fetch`/`EventSource`.

**REFACTOR:**

Свести проверку HTTP-статусов и JSON event parsing к небольшим внутренним
helpers без утечки DOM-логики.

**Точная команда теста:**

```sh
npm --prefix frontend test
```

## Задача 3. Подключить UI к dialog/SSE lifecycle

**Связанные требования:** REQ-004–REQ-013.

**Критерии приёмки:** hardcoded ответ удалён; форма проходит состояния
connecting/ready/submitting/processing/reconnecting/error; user message и SSE
ответ отображаются в правильном порядке и только через `textContent`.

**Зависимости:** задача 2.

**Файлы:**

- `frontend/src/index.html`;
- `frontend/src/script.js`;
- `frontend/src/styles.css`.

**Действия:**

1. Сделать browser script ES-модулем, добавить идентификатор/ARIA статусу и
   начальный disabled формы.
2. Перенести lifecycle из эталонного `/agent_test`: create dialog, ready,
   submit, pending event buffer, delta aggregation, end/error/reconnect/close.
3. Сохранить chips/autosize/Enter и исключить `innerHTML` для динамического
   текста.
4. Добавить минимальные стили disabled/error статусов без редизайна страницы.

**Проверка:**

```sh
npm --prefix frontend test
npm --prefix frontend run build
```

Проверка UI-состояний в Node входит в итоговый verify.

## Задача 4. Обновить контракты и документацию

**Связанные требования:** REQ-003, REQ-017.

**Критерии приёмки:** документация описывает две команды запуска, proxy target,
реальный dialog/SSE flow и ограничения; больше не утверждает, что frontend
показывает демонстрационный ответ.

**Зависимости:** задачи 1–3.

**Файлы:**

- `frontend/README.md`;
- `docs/README.md`;
- `docs/dialogs.md`;
- `docker/README.md`;
- `AGENTS.md`.

**Действия:**

1. Описать npm/Vite команды и `BACKEND_URL`.
2. Обновить глобальную карту и страницу dialog API с frontend proxy flow.
3. Исправить Docker-инструкцию: результат фонового запуска доступен через SSE
   и основной frontend.
4. Зафиксировать реализованную frontend-интеграцию и сохранение no-CORS/no-
   Compose-frontend границ в `AGENTS.md`.

**Проверка ревью:**

```sh
rg -n "Vite|BACKEND_URL|EventSource|frontend" frontend/README.md docs/README.md docs/dialogs.md docker/README.md AGENTS.md
```

Автоматические тесты документации не добавляются.

## Задача 5. Выполнить итоговый verify

**Связанные требования:** REQ-001–REQ-017.

**Критерии приёмки:** сборка, frontend/backend tests и Python lint зелёные;
Node-тесты подтверждают dialog/SSE lifecycle и сборку delta в один ответ,
локальные HTTP-запросы подтверждают Vite proxy для POST и SSE; scope не
расширен.

**Зависимости:** задачи 1–4.

**Изменяемые файлы:** только
`specs/changes/frontend-agent-integration/verification.md` после успешной
проверки.

**Команды:**

```sh
npm --prefix frontend run build
npm --prefix frontend run test:proxy
make test
make lint
git diff --check
```

**Runtime-проверка:**

1. Запустить локальный fake HTTP backend и Vite dev server программно из Node.
2. HTTP-запросами подтвердить выдачу страницы, создание диалога через proxy и
   передачу SSE с несколькими delta.
3. Node-тестами с fake DOM, `fetch` и `EventSource` подтвердить `ready`,
   блокировку формы, порядок user/assistant, delta, ошибки и переподключение.
4. Проверить отсутствие CORS middleware и frontend service в Compose.

## Итоговая проверка реализации

1. Сопоставить каждый REQ и критерий приёмки с Node-тестом, HTTP/SSE-проверкой или ревью.
2. Убедиться, что backend API/SSE code не менялся, `/agent_test` сохранён, CORS
   не добавлен и frontend не попал в Compose.
3. Проверить, что `node_modules/` и `frontend/dist/` отсутствуют в Git status.
4. Записать результаты и известные ограничения в `verification.md`, затем
   установить статус `done`.
