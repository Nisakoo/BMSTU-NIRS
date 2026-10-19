# План: надёжность каталога и хранилища знаний

## Основание

План реализует согласованную спецификацию
`specs/changes/knowledge-hardening/spec.md`: сначала рефакторинг без
изменения поведения, затем исправления и версия формата. Изменение
выполняется в ветке `feat/knowledge-postgres-store` отдельным коммитом до PR.

## Решения и зависимости

- Рефакторинг идёт первым: существующие тесты подтверждают, что поведение не
  изменилось, а исправления потом ложатся на очищенный код.
- Домен получает реестр `ENTITY_KINDS: dict[EntityType, EntityKind]`, где
  `EntityKind` хранит модель и поле `KnowledgeSet`. `ENTITY_TYPES`,
  `ENTITY_FIELDS` и таблица моделей адаптера пакета выводятся из него.
- Правила целостности возвращают `Violation` и принимают `unverified`
  отдельным параметром. `Issue` с файлом и строкой переезжает в
  `package.py`; адреса `db:<тип>/<id>` строит use case загрузки.
- Преобразователи агрегатов выносятся в `rag/postgres_mappers.py`: у каждого —
  корневая и дочерние таблицы, `to_rows(entity)` и `from_rows(rows)`.
  `postgres.py` оставляет транзакцию, блокировку, журнал и перевод ошибок.
- `postgres_store` в CLI переводит ошибку `load_config` в собственное
  исключение `ConfigurationError`; общий перехват `ValidationError` в CLI
  убирается. Адаптер переводит `ValidationError` при сборке моделей из строк
  в `KnowledgeDataInvalidError`, use case — в `stored_data_invalid`.
- `ChangeCounts` переезжает в `ports.py`, `LoadSummary.counts` типизирован.
- `package.yaml` читается тем же безопасным загрузчиком YAML и проверяется
  моделью `PackageManifest` (`format_version: Literal[1]`).
- `format_version` добавляется колонкой в `rag_revisions` прямо в миграции
  `0003` и в `rag/tables.py`; тест сравнения схемы это подтверждает.
- Тест `CHECK`: литералы из `pg_get_constraintdef` сравниваются с реестрами
  как множества.

## Порядок реализации

1. Реестр типов и вывод деталей файлов из домена.
2. Преобразователи агрегатов PostgreSQL.
3. Ошибки загрузки и типизированный итог.
4. Нормализация имён.
5. Версия формата пакета и снимков.
6. `CHECK` и символьные ссылки.
7. Документация.
8. Verify.

## Задача 1. Реестр типов и домен без файлов

**Связанные требования:** REQ-010–REQ-012.

**Критерии приёмки:** домен не импортирует адаптеры и не содержит `Issue`
и `unverified`; один реестр типов; тест полноты реестров; все прежние тесты
проходят.

**Файлы:** `rag/models.py`, `rag/integrity.py`, `rag/package.py`,
`rag/services.py`, `tests/unit/rag/test_registry.py`.

**Тест:** `uv run --project backend --locked pytest backend/tests/unit/rag`.

## Задача 2. Преобразователи агрегатов

**Связанные требования:** REQ-013.

**Критерии приёмки:** чтение и запись каждого агрегата описаны в одном
преобразователе; контрактный набор и подсчёт запросов проходят без
изменений.

**Файлы:** `rag/postgres_mappers.py`, `rag/postgres.py`.

**Тест:** `TEST_DATABASE_URL=… uv run --project backend --locked pytest backend/tests/integration/rag`.

## Задача 3. Ошибки загрузки и итог

**Связанные требования:** REQ-001, REQ-002, REQ-007.

**Критерии приёмки:** ошибка конфигурации и порча данных дают разные коды;
`LoadSummary.counts` — модели `ChangeCounts`.

**Файлы:** `rag/cli.py`, `rag/ports.py`, `rag/services.py`, `rag/postgres.py`,
тесты CLI, загрузки и хранилища.

**Тест (RED → GREEN):** unit-тесты CLI и use case с хранилищем, которое
выбрасывает `KnowledgeDataInvalidError`; интеграционный тест повреждённой
строки.

## Задача 4. Нормализация имён

**Связанные требования:** REQ-003.

**Файлы:** `rag/models.py`, `tests/unit/rag/test_models.py`,
`tests/unit/rag/test_integrity.py`.

**Тест (RED → GREEN):** разложенная «ё», `casefold`, конфликт имён.

## Задача 5. Версия формата

**Связанные требования:** REQ-004–REQ-006.

**Критерии приёмки:** пакет без `package.yaml` или с другой версией
отвергается; ревизии хранят `format_version`; `schema` выводит версию.
Тестовые пакеты получают `package.yaml` общим помощником.

**Файлы:** `rag/models.py`, `rag/package.py`, `rag/ports.py`,
`rag/memory.py`, `rag/postgres.py`, `rag/tables.py`, миграция `0003`, тесты.

**Тест:** unit и интеграционные тесты RAG.

## Задача 6. `CHECK` и символьные ссылки

**Связанные требования:** REQ-008, REQ-009.

**Файлы:** `rag/package.py`, `tests/unit/rag/test_package.py`,
`tests/integration/rag/test_schema.py`.

## Задача 7. Документация

**Связанные требования:** REQ-014.

**Файлы:** `docs/knowledge.md`, `docs/rag.md`.

**Проверка:** ревью; примеры страницы, извлечённые в пакет, проходят `check`.

## Задача 8. Verify

`make lint`, `make test`, PostgreSQL-тесты RAG и других модулей на временной
БД, `verification.md`, статус `done`, локальный коммит.
