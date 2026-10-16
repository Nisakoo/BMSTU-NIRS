# План: защита ручек диалогов, редиректы и создание администратора

Спецификация: [spec.md](./spec.md).

## Порядок

Сначала backend-защита ручек: от неё зависят ручные проверки frontend. Затем
команда создания администратора — без неё нельзя вручную проверить `/admin/`.
После этого общий frontend-модуль проверки сессии и его подключение к
`/login/`, чату и `/admin/`. Документация — последней задачей.

Рискованные предположения, проверяемые первыми:

- FastAPI выполняет зависимости роутера до валидации path-параметров и тела,
  но синтаксически некорректный JSON отклоняет `422` ещё до зависимостей
  (проверено прототипом). Поэтому `submit_message` читает и валидирует тело
  внутри обработчика после `current_user`, сохраняя формат ошибки FastAPI
  `{"detail": [...]}` через `RequestValidationError` (задача 1).
- Без `auth_service` ручки диалогов должны отвечать `503`, а не `500`:
  обработчик `AuthHTTPError` регистрируется в `create_app` всегда, а
  `current_user` при отсутствии сервиса возвращает `unavailable` (задача 1).
- `docker compose run` выделяет TTY, поэтому `getpass` работает внутри
  контейнера (задача 2, ручная проверка).

## Задача 1. Защита ручек диалогов на backend

**Требования:** REQ-001…REQ-005.

**Критерии приёмки:** три ручки диалогов отвечают `401`
`{"error":"unauthorized"}` без cookie, с некорректным токеном и токеном в
blacklist, в том числе для несуществующего диалога, невалидного UUID, пустого
и синтаксически некорректного тела; `503` `{"error":"unavailable"}` при
недоступности blacklist и при `create_app` без `auth_service`; с
действительным токеном все существующие сценарии диалогов и SSE проходят без
изменений ожидаемых ответов; `/agent_test` и ручки аутентификации открыты.

**Зависимости:** нет.

**Файлы:**

- `backend/src/smeshariki_ai/api/app.py` — роутер диалогов с
  `dependencies=[Depends(current_user)]`, разбор тела `submit_message` после
  аутентификации, регистрация обработчика ошибок аутентификации;
- `backend/src/smeshariki_ai/api/auth.py` — `current_user` без
  `auth_service` возвращает `unavailable`; функция регистрации обработчика;
- `backend/tests/integration/api/api_auth_support.py` — тестовый
  `auth_service`, принимающий фиксированный токен, и helper сборки
  аутентифицированного клиента;
- `backend/tests/integration/api/test_auth.py` — новые тесты защиты;
- `backend/tests/integration/api/{test_dialogs,test_sse,test_litellm_provider}.py`
  — клиенты получают cookie через helper.

**Проверка:**

```sh
uv run --project backend --locked pytest backend/tests/integration/api backend/tests/unit/test_bootstrap.py
```

## Задача 2. Команда создания администратора

**Требования:** REQ-016…REQ-020.

**Критерии приёмки:** функция создания администратора валидирует поля через
`Credentials`, хеширует пароль `Argon2PasswordHasher` и создаёт пользователя с
ролью `admin` через `UserStore`; хеш проходит `verify`; занятый логин в другом
регистре, неверные поля, несовпадение паролей и `AuthUnavailableError` дают
ненулевой код и сообщение без пароля; запись не создаётся. `AuthService.register`
использует ту же общую функцию создания пользователя, поэтому хеширование не
дублируется. `make create-admin LOGIN=<login>` применяет миграции и запускает
команду в Compose с интерактивным вводом пароля.

**Зависимости:** нет.

**Файлы:**

- `backend/src/smeshariki_ai/auth/users.py` — общая
  `create_user(users, hasher, credentials, role, now)`; используется
  `AuthService.register` и командой;
- `backend/src/smeshariki_ai/auth/service.py` — `register` через
  `create_user`;
- `backend/src/smeshariki_ai/create_admin.py` — CLI
  `python -m smeshariki_ai.create_admin --login <login>`: ввод пароля через
  инжектируемую функцию (`getpass` по умолчанию), вывод через инжектируемый
  поток, production-зависимости `PostgresUserStore` и `load_config().database`;
- `Makefile` — цель `create-admin`, зависящая от `migrate`;
- `backend/tests/unit/auth/test_create_admin.py`.

**Проверка:**

```sh
uv run --project backend --locked pytest backend/tests/unit/auth
```

Ручная: `make run`, затем `make create-admin LOGIN=admin` в соседнем
терминале; пароль не отображается; вход созданным администратором успешен.

## Задача 3. Frontend: клиент и общий модуль проверки сессии, страница входа

**Требования:** REQ-006, REQ-007, REQ-014, REQ-015.

**Критерии приёмки:** `AuthApi.refresh()` следует REQ-006; `checkSession`
возвращает `user` (из `me()` или из ответа `refresh()`, который по контракту
содержит актуального пользователя), `anonymous` (оба `401`) или
`unavailable` (иначе) и вызывает `refresh()` не более одного раза;
`homeFor(user)` возвращает `/admin/` для `admin` и `/` для `user`; `/login/`
при открытии и после входа/регистрации переходит по роли.

**Зависимости:** задача 1 только для ручной проверки.

**Файлы:**

- `frontend/src/auth-api.js` — `refresh()`;
- `frontend/src/auth-session.js` — `checkSession`, `refreshSession`,
  `homeFor`, константы путей;
- `frontend/src/login/login.js`;
- `frontend/tests/auth-api.test.js`, `frontend/tests/auth-session.test.js`,
  `frontend/tests/login-ui.test.js`.

**Проверка:**

```sh
npm --prefix frontend test
```

## Задача 4. Frontend: чат

**Требования:** REQ-008…REQ-012.

**Критерии приёмки:** диалог создаётся только после `user`; `anonymous` —
`location.replace("/login/")` без `POST /dialogs`; `unavailable` — статус
недоступности и повтор проверки через 3 секунды (существующий единственный
таймер повтора); `401` у создания диалога или отправки — одна попытка
`refresh()` и повтор операции, затем переход на `/login/`; реплика
пользователя добавляется один раз; ошибка SSE запускает проверку сессии
(не более одной одновременно): `anonymous` — переход, `user` и закрытый
`EventSource` — новое соединение к тому же диалогу, не более одного
переоткрытия до следующего `ready`.

**Зависимости:** задача 3.

**Файлы:**

- `frontend/src/agent-api.js` — код `unauthorized` для `401` у
  `createDialog`/`submitMessage`; `isClosed()` у соединения по
  `readyState`;
- `frontend/src/script.js`;
- `frontend/tests/agent-api.test.js`, `frontend/tests/ui.test.js` — fake
  `fetch` отвечает на `/users/me` и `/auth/refresh`, fake `location`.

**Проверка:**

```sh
npm --prefix frontend test
```

## Задача 5. Frontend: панель администратора

**Требования:** REQ-013.

**Критерии приёмки:** до проверки сессии demo-данные не отображаются;
`admin` — панель монтируется как раньше; `user` — переход на `/`;
`anonymous` — на `/login/`; `unavailable` — сообщение о недоступности без
demo-данных.

**Зависимости:** задача 3.

**Файлы:**

- `frontend/src/admin/admin.js` — `mountAdminPage` с guard перед
  `mountDashboard`/`mountAdminNavigation`;
- `frontend/src/admin/index.html`, `frontend/src/admin/admin.css` — скрытие
  содержимого до проверки и блок сообщения;
- `frontend/tests/admin-ui.test.js`.

**Проверка:**

```sh
npm --prefix frontend test
```

## Задача 6. Документация

**Требования:** REQ-021.

**Критерии приёмки:** `docs/auth.md` (защита ручек, проверка сессии,
редиректы по роли, `make create-admin`, сокращённый список «Что пока не
реализовано»), `docs/dialogs.md` (`401`/`503` у ручек диалогов),
`frontend/README.md`, `docker/README.md`, разделы `AGENTS.md` и при
необходимости `docs/README.md` соответствуют реализации.

**Зависимости:** задачи 1–5.

**Проверка:** ревью документации; итоговые `make test` и `make lint`.
