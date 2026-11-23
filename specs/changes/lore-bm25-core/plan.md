# План: BM25-поиск по лору

## Основание

План реализует `specs/changes/lore-bm25-core/spec.md`. Изменение остаётся
внутри RAG: домен BM25, YAML-пакет лора, PostgreSQL-индекс, загрузка и поиск.
`agent`, `application`, `api`, `bootstrap.py` и `config.py` не меняются.

## Решения и зависимости

- Production-поиск считает BM25 в PostgreSQL по таблицам postings, термов,
  чанков и статистики. В память backend корпус не загружается.
- `InMemoryBm25Index` реализует тот же порт и используется только в unit-тестах
  и benchmark; контрактный тест сравнивает его порядок с PostgreSQL.
- `pymorphy3` добавляется как зависимость backend. `SimpleAnalyzer` остаётся
  для тестов и сравнения; production-загрузка и поиск используют
  `MorphAnalyzer`.
- Формат пакета — YAML: `package.yaml` и `documents/<id>.yaml`.
- Загрузка заменяет корпус целиком в одной транзакции под advisory lock;
  документы, чанки и postings пишутся пакетами, `df` и `avgdl` считаются
  SQL-агрегатами, а не удержанием всего корпуса в памяти.
- `lore-check` не читает environment; `lore-load` и `lore-search` загружают
  только `DatabaseConfig` через существующий `load_config`.
- Названия таблиц и портов фиксированы в спецификации; миграция аддитивная.

## Порядок реализации

1. Ядро BM25 и анализатор.
2. Модели, чанкование и YAML-пакет.
3. Порты, in-memory индекс и use cases.
4. PostgreSQL: таблицы, миграция, загрузка и поиск.
5. CLI и Make-цели.
6. Документация.
7. Полная проверка изменения.

## Задача 1. Ядро BM25 и анализатор

**Требования:** REQ-001–REQ-005.

**Критерии:** чистые функции IDF и BM25; параметры `k1=1.2`, `b=0.75`;
пустой корпус и нулевые значения безопасны; `SimpleAnalyzer` и
`MorphAnalyzer` дают одинаковый контракт `terms()`; `pymorphy3` установлен и
зафиксирован в lock-файле.

**Файлы:** `rag/lore/models.py`, `rag/lore/bm25.py`,
`rag/lore/analyzer.py`, `rag/lore/__init__.py`,
`backend/pyproject.toml`, `backend/uv.lock`,
`backend/tests/unit/rag/lore/test_bm25.py`,
`backend/tests/unit/rag/lore/test_analyzer.py`.

**Зависимости:** нет.

**Проверка:**
`uv run --project backend --locked pytest backend/tests/unit/rag/lore/test_bm25.py backend/tests/unit/rag/lore/test_analyzer.py -q`.

## Задача 2. Чанкование и YAML-пакет

**Требования:** REQ-015–REQ-017, REQ-001.

**Критерии:** детерминированные чанки 150–250 слов с перекрытием; границы
документа не пересекаются; пакет проверяет manifest, поля, id, лишние файлы и
симлинки; ошибки адресуются файлом и полем; `lore-check` не читает
environment.

**Файлы:** `rag/lore/chunking.py`, `rag/lore/package.py`,
`backend/tests/unit/rag/lore/test_chunking.py`,
`backend/tests/unit/rag/lore/test_package.py`.

**Зависимости:** задача 1.

**Проверка:**
`uv run --project backend --locked pytest backend/tests/unit/rag/lore/test_chunking.py backend/tests/unit/rag/lore/test_package.py -q`.

## Задача 3. Порты, in-memory индекс и use cases

**Требования:** REQ-006–REQ-009, REQ-001, REQ-018.

**Критерии:** `LoreStore`, `LoreIndex`, `LoreDocumentSource` — порты;
`InMemoryBm25Index` строит postings и ищет top-k; `SearchLore` и `LoadLore`
зависят только от портов; пустой запрос и пустой корпус дают пустую выдачу.

**Файлы:** `rag/lore/ports.py`, `rag/lore/index.py`,
`rag/lore/services.py`,
`backend/tests/unit/rag/lore/test_index.py`,
`backend/tests/unit/rag/lore/test_services.py`.

**Зависимости:** задачи 1–2.

**Проверка:**
`uv run --project backend --locked pytest backend/tests/unit/rag/lore/test_index.py backend/tests/unit/rag/lore/test_services.py -q`.

## Задача 4. PostgreSQL: таблицы, миграция, загрузка и поиск

**Требования:** REQ-010–REQ-014, REQ-006–REQ-009.

**Критерии:** миграция `0013_lore_bm25` создаёт `rag_lore_*` и совпадает с
`rag/lore/tables.py`; `PostgresLoreStore.replace` атомарно заменяет корпус и
пишет журнал; `PostgresBm25Index.search` считает BM25 одним set-based
запросом; `InMemoryBm25Index` и PostgreSQL дают одинаковый порядок на
контрактном наборе; схема не готова → безопасная ошибка.

**Файлы:** `rag/lore/tables.py`, `rag/lore/postgres.py`,
`db/migrations/versions/0013_lore_bm25.py`,
`backend/tests/integration/rag/test_lore_postgres.py`,
`backend/tests/integration/rag/test_lore_schema.py`.

**Зависимости:** задачи 1–3.

**Проверка:**
`make test-integration PYTEST_ARGS="backend/tests/integration/rag/test_lore_postgres.py backend/tests/integration/rag/test_lore_schema.py -q"`.

## Задача 5. CLI и Make-цели

**Требования:** REQ-018–REQ-020.

**Критерии:** `lore-check`, `lore-load`, `lore-search` работают с кодами
`0/1/2`; JSON-вывод стабилен; `lore-check` не требует environment;
`lore-load` пишет только отчёт в stdout; Make-цели аддитивны; логи не содержат
текста запросов и документов.

**Файлы:** `rag/cli.py`, `Makefile`,
`backend/tests/unit/rag/lore/test_lore_cli.py`,
`backend/tests/integration/rag/test_lore_cli.py`.

**Зависимости:** задачи 2–4.

**Проверка:**
`uv run --project backend --locked pytest backend/tests/unit/rag/lore/test_lore_cli.py -q`.

## Задача 6. Документация

**Требования:** REQ-021.

**Критерии:** `docs/lore.md` описывает формулу, формат, чанкование, таблицы,
команды, масштабирование и ограничения; `docs/rag.md`, `docs/database.md` и
`docs/README.md` обновлены; `AGENTS.md` и `bootstrap.py` не изменены.

**Файлы:** `docs/lore.md`, `docs/rag.md`, `docs/database.md`,
`docs/README.md`.

**Зависимости:** задачи 4–5.

**Проверка:** ревью документации и diff общих файлов.

## Задача 7. Полная проверка изменения

**Требования:** REQ-022.

**Критерии:** unit-, PostgreSQL- и Compose-тесты проходят; миграция
обратима; загрузка синтетического пакета и поиск воспроизведены вручную;
`make lint`, `make test`, `make test-integration` успешны.

**Файлы:** `specs/changes/lore-bm25-core/verification.md`.

**Зависимости:** задачи 1–6.

**Проверка:** `make lint`, `make test`, `make test-integration`; ручные
`make lore-check`, `make lore-load`, `make lore-search` на синтетическом
пакете.
