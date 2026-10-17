# База данных

[← Глобальный каталог](./README.md)

Backend хранит постоянные данные в PostgreSQL 17. База — инфраструктурная
зависимость backend: она работает в отдельном Compose-контейнере `postgres`, но
подключение, схема и миграции принадлежат пакету `smeshariki_ai.db`.

Схема включает таблицы аутентификации (миграция `0001`) и постоянную историю
диалогов пользователя (миграция `0002`).

| Таблица | Назначение | Состояние |
| --- | --- | --- |
| `users` | Учётные записи и роли | Реализовано, миграция `0001` |
| `refresh_sessions` | Refresh-токены и их ротация | Реализовано, миграция `0001` |
| `dialogs` | Диалоги пользователя | Реализовано, миграция `0002` |
| `messages` | Сообщения диалога | Реализовано, миграция `0002` |
| `message_feedback` | Оценки ответов ассистента (1–5) | Реализовано, миграции `0003`, `0004` |

## Где находится реализация

- [`db/tables.py`](../backend/src/smeshariki_ai/db/tables.py) — описание
  таблиц в SQLAlchemy Core;
- [`db/stores.py`](../backend/src/smeshariki_ai/db/stores.py) —
  `PostgresUserStore` и `PostgresRefreshSessionStore`;
- [`db/history.py`](../backend/src/smeshariki_ai/db/history.py) —
  `PostgresHistoryStore` (контракт `HistoryStore` из [диалогов](./dialogs.md));
- [`db/engine.py`](../backend/src/smeshariki_ai/db/engine.py) — ленивый async
  engine (`asyncpg`);
- [`db/migrations/`](../backend/src/smeshariki_ai/db/migrations/) — Alembic
  environment и версии миграций;
- [`db/migrate.py`](../backend/src/smeshariki_ai/db/migrate.py) — команда
  применения миграций.

## Схема

```mermaid
erDiagram
    users ||--o{ refresh_sessions : "владеет"
    users ||--o{ dialogs : "владеет"
    dialogs ||--o{ messages : "содержит"
    refresh_sessions |o--o| refresh_sessions : "replaced_by"

    users {
        uuid id PK
        text login "3-32 [A-Za-z0-9_.-]"
        text password_hash "argon2id PHC"
        text role "user | admin"
        timestamptz created_at
        timestamptz updated_at
    }
    refresh_sessions {
        uuid id PK "= sid в access JWT"
        uuid user_id FK
        uuid family_id
        bytea token_hash UK "SHA-256"
        timestamptz created_at
        timestamptz expires_at
        timestamptz revoked_at "NULL = активна"
        uuid replaced_by FK
    }
    dialogs {
        uuid id PK "совместим с текущим dialog_id"
        uuid user_id FK
        text title "NULL"
        timestamptz created_at
        timestamptz updated_at
    }
    messages {
        bigint id PK "identity"
        uuid dialog_id FK
        int position
        text role "user | assistant"
        text content
        timestamptz created_at
    }
```

### `users`

| Столбец | Тип | Ограничения |
| --- | --- | --- |
| `id` | `uuid` | PK; UUIDv4 генерирует приложение |
| `login` | `text` | `NOT NULL`, `CHECK login ~ '^[A-Za-z0-9_.-]{3,32}$'` |
| `password_hash` | `text` | `NOT NULL`, строка argon2id в формате PHC |
| `role` | `text` | `NOT NULL DEFAULT 'user'`, `CHECK role IN ('user','admin')` |
| `created_at`, `updated_at` | `timestamptz` | `NOT NULL DEFAULT now()` |

Индекс `users_login_lower_key` — `UNIQUE (lower(login))`: логин хранится в
исходном регистре, а уникальность и поиск выполняются без учёта регистра.

### `refresh_sessions`

| Столбец | Тип | Ограничения |
| --- | --- | --- |
| `id` | `uuid` | PK; передаётся в access JWT как `sid` |
| `user_id` | `uuid` | `NOT NULL`, FK `users(id) ON DELETE CASCADE`, индекс |
| `family_id` | `uuid` | `NOT NULL`, индекс; общий для цепочки ротаций одного входа |
| `token_hash` | `bytea` | `NOT NULL UNIQUE`; SHA-256 от refresh-токена |
| `created_at`, `expires_at` | `timestamptz` | `NOT NULL` |
| `revoked_at` | `timestamptz` | `NULL` — сессия активна |
| `replaced_by` | `uuid` | FK `refresh_sessions(id) ON DELETE SET NULL` |

Ротация выполняется одной транзакцией: вставка новой сессии и условный
`UPDATE ... WHERE revoked_at IS NULL` старой. Если старая уже отозвана
параллельным запросом, транзакция откатывается и сервис считает это повторным
использованием токена. Сам refresh-токен в базе не хранится.

### `dialogs`

| Столбец | Тип | Ограничения |
| --- | --- | --- |
| `id` | `uuid` | PK; тот же UUID, что сейчас возвращает `POST /api/v1/dialogs` |
| `user_id` | `uuid` | `NOT NULL`, FK `users(id) ON DELETE CASCADE` |
| `title` | `text` | `NULL` |
| `created_at`, `updated_at` | `timestamptz` | `NOT NULL DEFAULT now()` |

Индекс `ix_dialogs_user_id_updated_at` — `(user_id, updated_at DESC)` для
списка диалогов пользователя от новых к старым. `title` задаётся из первого
запроса при первом сохранении сообщений и затем не меняется; `updated_at`
обновляется при каждом добавлении сообщений.

### `messages`

| Столбец | Тип | Ограничения |
| --- | --- | --- |
| `id` | `bigint` | PK, `GENERATED ALWAYS AS IDENTITY` |
| `dialog_id` | `uuid` | `NOT NULL`, FK `dialogs(id) ON DELETE CASCADE` |
| `position` | `int` | `NOT NULL`, `UNIQUE (dialog_id, position)` |
| `role` | `text` | `NOT NULL`, `CHECK role IN ('user','assistant')` |
| `content` | `text` | `NOT NULL` |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` |

`position` задаёт порядок и делает атомарное добавление пары «пользователь —
ассистент» проверяемым на конфликт (`messages_dialog_id_position_key`).
Добавление выполняется одной транзакцией: `SELECT ... FOR UPDATE` строки
диалога сериализует параллельные добавления, новые позиции продолжают
максимальную, а `updated_at` и `title` диалога обновляются в той же
транзакции. Tool calls и tool results не хранятся.

### `message_feedback`

| Столбец | Тип | Ограничения |
| --- | --- | --- |
| `message_id` | `bigint` | PK, FK `messages(id) ON DELETE CASCADE` |
| `score` | `smallint` | `NOT NULL`, `CHECK score BETWEEN 1 AND 5` |
| `created_at`, `updated_at` | `timestamptz` | `NOT NULL DEFAULT now()` |

Балл 1–5 соответствует мордашкам от грустного Ёжика до Кроша в восторге.
Миграция `0004` заменила столбец `value` (`like`/`dislike`) на `score`,
перенеся `like` → 5 и `dislike` → 1; её downgrade возвращает `value`
(3–5 → `like`, 1–2 → `dislike`). Оценка одна на ответ: её ставит владелец диалога, повторная оценка
заменяет прежнюю (`INSERT ... ON CONFLICT DO UPDATE`), снятие удаляет строку.
Перед записью хранилище проверяет, что сообщение — ответ ассистента в
диалоге этого пользователя. Удаление пользователя каскадно удаляет и оценки.

## Решения

- `role` — `text` с `CHECK`, а не PostgreSQL enum: новая роль добавляется
  миграцией ограничения без `ALTER TYPE`.
- UUID генерирует приложение, поэтому идентификаторы известны до вставки и
  совпадают с уже опубликованным форматом API.
- Удаление пользователя каскадно удаляет его refresh-сессии, диалоги и
  сообщения.
- Ошибки подключения и SQL адаптеры аутентификации превращают в
  `AuthUnavailableError`, адаптер истории — в `DialogStoreUnavailableError`;
  engine создаётся с `hide_parameters=True`, чтобы хеши не попадали в текст
  исключений.

## Миграции

Миграции — Alembic-скрипты в пакете backend, источник истины для схемы.
`tables.py` повторяет их для запросов и должен меняться вместе с ними.

```sh
# В Compose: одноразовый сервис migrate выполняет перед стартом backend
python -m smeshariki_ai.db.migrate
# Вручную из корня репозитория (поднимает postgres при необходимости)
make migrate
```

Команда берёт `DATABASE_URL` через `load_config`, поэтому ей нужен тот же
environment, что и backend; Compose передаёт его общим YAML-якорем. Отдельный
`alembic.ini` не используется: `script_location` и engine задаются в
`migrate.py`. Новая версия добавляется файлом в `db/migrations/versions/`
со следующим номером ревизии.

## SDD-артефакты

- [спецификация](../specs/changes/backend-auth-jwt/spec.md);
- [спецификация постоянной истории](../specs/changes/user-dialog-history/spec.md),
  [план](../specs/changes/user-dialog-history/plan.md);
- [план](../specs/changes/backend-auth-jwt/plan.md),
  [результат проверки](../specs/changes/backend-auth-jwt/verification.md).
