# План: инструмент агента `lookup_knowledge`

## Основание

План реализует согласованную спецификацию
`specs/changes/knowledge-lookup-tool/spec.md` в ветке
`feat/knowledge-lookup-tool` поверх `feat/postgres-test-env`.

## Решения и зависимости

- Миграция `0004` добавляет `normalized_title` как nullable, заполняет её
  построчно в Python через `normalize_name` (SQL `lower()` не совпадает с
  `casefold` и заменой «ё»), затем ставит `NOT NULL`, `CHECK` непустоты и
  индекс `rag_episodes_normalized_title_idx`. Миграция импортирует
  `normalize_name` из домена: функция — часть контракта ключа, а её
  изменение и так требует новой миграции.
- Чтение агрегатов по списку `id` выносится из `_PostgresTransaction` в общую
  функцию модуля `postgres.py`, принимающую соединение и необязательный
  фильтр владельца; `read_all` и `find` используют её с одними `MAPPERS`.
- `find` в PostgreSQL: запросы `id` по ключу (таблицы имён трёх типов и
  `normalized_title` эпизодов, плюс корни по `id`), затем агрегаты только тех
  типов, где есть совпадения, затем названия ссылок одним запросом на тип
  (`rag_continuities`, `rag_works`, имена на позиции `0`, названия эпизодов
  не нужны). Число запросов ограничено числом таблиц.
- Транзакция поиска — `engine.connect()` с
  `execution_options(isolation_level="REPEATABLE READ", postgresql_readonly=True)`.
- `InMemoryKnowledgeStore` реализует `KnowledgeReader` над текущим
  состоянием без блокировки загрузки: состояние заменяется целиком при
  фиксации, поэтому чтение видит согласованный снимок.
- Поле журнала `match_count` добавляется одной строкой в `_SAFE_FIELDS`
  `observability.py` (аддитивно); событие описывается в `docs/logging.md`.
- Подключение в `bootstrap.py` (REQ-013) — отдельная последняя задача,
  выполняется только после согласия владельца agent.

## Порядок реализации

1. Ключ названия эпизода (рискованная часть: миграция на данных).
2. Порт чтения и две реализации.
3. Use case и карточки.
4. Инструмент.
5. Документация.
6. Подключение в `bootstrap.py` (после согласия).
7. Verify.

## Задача 1. Ключ названия эпизода

**Требования:** REQ-016.

**Критерии приёмки:** схема совпадает с `tables.metadata`; миграция на БД с
эпизодами заполняет ключ; `downgrade` до `0003` удаляет колонку, `upgrade`
возвращает; загрузка пишет ключ.

**Файлы:** `db/migrations/versions/0004_rag_episode_title_key.py`,
`rag/tables.py`, `rag/postgres_mappers.py`,
`backend/tests/integration/rag/test_schema.py`.

**Проверка:** `make test-integration PYTEST_ARGS=backend/tests/integration/rag`.

## Задача 2. Порт чтения

**Требования:** REQ-001–REQ-004, REQ-014.

**Критерии приёмки:** контрактные тесты на обеих реализациях: имя, алиас,
slug, название эпизода, регистр, «ё», пробелы, несколько типов, несколько
эпизодов, нет совпадений, названия ссылок, `has_knowledge`; PostgreSQL —
постоянное число запросов, read-only, ошибки схемы и недоступной БД.

**Файлы:** `rag/ports.py`, `rag/memory.py`, `rag/postgres.py`,
`backend/tests/integration/rag/test_reader_contract.py`.

**Проверка:** `make test-integration PYTEST_ARGS=backend/tests/integration/rag`.

## Задача 3. Use case и карточки

**Требования:** REQ-005–REQ-009, REQ-017.

**Критерии приёмки:** карточки всех типов с названиями вместо slug, порядок,
лимит 10, `total`, `truncated`, статусы, ошибки порта → `unavailable`,
событие журнала без текста запроса.

**Файлы:** `rag/lookup.py`, `observability.py`,
`backend/tests/unit/rag/test_lookup.py`.

**Проверка:** `uv run --project backend --locked pytest backend/tests/unit/rag/test_lookup.py`.

## Задача 4. Инструмент

**Требования:** REQ-010–REQ-012.

**Критерии приёмки:** определение в `ToolRegistry`, валидация аргументов,
JSON-выход с пояснениями.

**Файлы:** `rag/tools.py`, `backend/tests/unit/rag/test_tools.py`.

**Проверка:** `uv run --project backend --locked pytest backend/tests/unit/rag/test_tools.py`.

## Задача 5. Документация

**Требования:** REQ-015.

**Файлы:** `docs/rag.md`, `docs/knowledge.md`, `docs/logging.md`,
`docs/README.md`, `AGENTS.md`.

**Проверка:** ревью; `git diff` общих файлов без удалённых строк.

## Задача 6. Подключение в `bootstrap.py`

**Требования:** REQ-013, REQ-014.

**Зависимости:** согласие владельца agent.

**Файлы:** `bootstrap.py`, `backend/tests/unit/test_bootstrap.py`.

**Проверка:** `uv run --project backend --locked pytest backend/tests/unit/test_bootstrap.py`.

## Задача 7. Verify

**Проверка:** `make lint`, `make test`, `make test-integration`;
`verification.md`; контроль ресурсов компьютера до и после прогонов.
