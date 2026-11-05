# План: смена пароля в настройках аккаунта

Спецификация: [spec.md](./spec.md). Пользователь одобрил спецификацию и
попросил выполнить весь цикл («делай»).

## Решения

- **Сервис.** `AuthService.change_password(access_token, current_password,
  new_password)` декодирует access-токен (как `authenticate`, с проверкой
  blacklist), читает пользователя по id, проверяет текущий пароль через
  `Argon2PasswordHasher.verify`, хеширует новый и сохраняет хеш, затем
  отзывает остальные refresh-сессии, сохраняя `claims.session_id`.
  Совпадение нового пароля с текущим проверяется после проверки текущего:
  иначе ответ `same_password` подтверждал бы угаданный пароль без проверки.
- **Хранилища.** `UserStore.get_password_hash(user_id) -> str | None` и
  `UserStore.set_password_hash(user_id, password_hash, updated_at)`;
  `RefreshSessionStore.revoke_user_sessions(user_id, keep_session_id, now)`.
  PostgreSQL: `UPDATE users SET password_hash, updated_at` и
  `UPDATE refresh_sessions SET revoked_at WHERE user_id AND id <> keep AND
  revoked_at IS NULL`. Миграция не нужна.
- **Ошибки.** `WrongPasswordError`, `SamePasswordError` наследуют
  `AuthError`; HTTP-слой переводит их в `400 wrong_password` и
  `422 same_password`.
- **HTTP.** `PUT /api/v1/users/me/password`: сначала `current_user`
  (`401`/`503` раньше разбора тела), затем `PasswordChange` (strict,
  `extra="forbid"`, оба поля `Password`), затем сервис.
- **Frontend-клиент.** `AuthApi.changePassword` отправляет `PUT` с
  `current_password` и `new_password`; на `422` читает код из тела
  (`same_password`, иначе `invalid_fields`).
- **Окно.** Разметка в `index.html` (скрытое `div.sai-settings` с
  `role="dialog"`), логика в `script.js` рядом с выходом; `Escape`
  обрабатывается в общем `keydown` первым. Запрос идёт через существующий
  `withSession`.

## Задача 1. Сервис и in-memory хранилища

**Требования:** REQ-001–003, REQ-005, REQ-006.

**Файлы:** `auth/models.py`, `auth/stores.py`, `auth/memory.py`,
`auth/service.py`, `auth/__init__.py`, `tests/unit/auth/test_auth_service.py`.

**Проверка:** `uv run --project backend --locked pytest
backend/tests/unit/auth`.

## Задача 2. HTTP-ручка

**Требования:** REQ-001–004, REQ-007.

**Файлы:** `api/auth.py`, `tests/integration/api/test_auth.py`.

**Проверка:** `uv run --project backend --locked pytest
backend/tests/integration/api/test_auth.py`.

## Задача 3. PostgreSQL-адаптеры

**Требования:** REQ-001, REQ-005.

**Файлы:** `db/stores.py`, `tests/integration/db/test_postgres_stores.py`.

**Проверка:** тесты с `TEST_DATABASE_URL` на временной PostgreSQL (без
переменной они пропускаются).

## Задача 4. Клиент API

**Требования:** REQ-011 (коды ошибок).

**Файлы:** `frontend/src/auth-api.js`, `frontend/tests/auth-api.test.js`.

**Проверка:** `node --test frontend/tests/auth-api.test.js`.

## Задача 5. Шестерёнка и окно настроек

**Требования:** REQ-008–014.

**Файлы:** `frontend/src/index.html`, `frontend/src/script.js`,
`frontend/src/styles.css`, `frontend/tests/ui.test.js`.

**Проверка:** `node --test frontend/tests/ui.test.js`, ручной просмотр
вёрстки.

## Задача 6. Документация

**Файлы:** `docs/auth.md`, `docs/README.md`, `frontend/README.md`,
`AGENTS.md`.

**Проверка:** ревью; затем `make lint` и `make test`.
