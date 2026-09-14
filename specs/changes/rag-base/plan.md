# План: базовый RAG — System Context и Structured Knowledge

## Основание

План реализует одобренную спецификацию
`specs/changes/rag-base/spec.md` и не включает работы из
`rag-retrieval` или `rag-index-evaluation`.

Результат этапа implement — запускаемый из корня репозитория базовый RAG:

- `make run` открывает локальный CLI;
- `context` возвращает версионируемый `SystemContext`;
- `lookup` возвращает `found`, `not_found` или `ambiguous`;
- `make test` запускает настоящие тесты Python-кода и завершается успешно.

## Архитектурные решения

### Размещение и зависимости

- Python-проект backend описывается в `backend/pyproject.toml`, lock-файл —
  `backend/uv.lock`.
- Команды из корня используют `uv run --project backend ...`.
- Дистрибутив называется `smeshariki-ai`, импортируемый пакет остаётся
  `smeshariki_ai`, используется Python 3.12.
- Runtime-зависимость — Pydantic 2; тестовая зависимость — Pytest. Конкретные
  совместимые версии фиксирует `uv.lock`.
- Данные пакета включаются в дистрибутив настройкой `pyproject.toml`, чтобы
  файловый адаптер одинаково работал из checkout и установленного wheel.

### Модули

```text
backend/src/smeshariki_ai/rag/
├── __init__.py           # публичные модели, порт и сервис
├── __main__.py           # запуск через python -m smeshariki_ai.rag
├── cli.py                # локальный интерактивный adapter
├── git_store.py          # файловая реализация порта
├── in_memory.py          # детерминированная тестовая реализация порта
├── models.py             # Pydantic-модели и KnowledgeCatalog
├── ports.py              # StructuredKnowledgeStorePort
├── service.py            # get_system_context и lookup_knowledge
└── data/
    ├── system_context.md
    └── knowledge.json
```

Это физическая структура только изменения `rag-base`; новые верхнеуровневые
сервисы и Docker-файлы не создаются.

### Форматы данных

`system_context.md` имеет первую строку:

```text
<!-- system-context-version: 1 -->
```

Оставшийся текст без служебного перевода строки в начале становится `prompt`.
Изменение смыслового текста требует увеличения версии.

`knowledge.json` содержит корневой объект с `schema_version` и массивом
`records`. Каждый элемент массива валидируется как discriminated union по
`entity_type`. `KnowledgeCatalog` является внутренним aggregate root для полной
проверки ID, алиасов и ссылок; он не добавляет поля в согласованные профили.

### Разрешение рискованных неоднозначностей

1. `SourceRef.locator` принимает либо `<непустой путь>:<номер строки от 1>`, либо
   `<непустой episode_id>:<MM:SS|HH:MM:SS>`. Пробелы и переводы строк запрещены.
2. Глобальная уникальность проверяется между нормализованными значениями поля
   `aliases`. Совпадающие канонические `name` разных version-specific записей
   разрешены и являются штатным источником результата `ambiguous`.
3. При lookup записи сначала ограничиваются `entity_type`, затем точным
   совпадением нормализованного ID/name/alias, затем OR-фильтром канона.
   Совпадения одной записи по нескольким ключам дедуплицируются по
   `(entity_type, id)`.
4. `KnowledgeNotFound` содержит `entity_type`, нормализованный `key` и
   нормализованный стабильный список `canon_variants`;
   `KnowledgeAmbiguous` дополнительно содержит те же параметры запроса и
   отсортированные `candidates`.
5. Списочные поля сохраняют редакционный порядок из JSON. Множества,
   образованные вычислением, сериализуются только после стабильной сортировки.
6. Инфраструктурные и validation-ошибки не входят в три штатных lookup-статуса и
   представлены типизированными исключениями с безопасным сообщением.

## Зависимости и порядок

1. Сначала создаются Python-проект, строгие модели и aggregate validation:
   последующие сервисы не должны строиться на незафиксированной схеме.
2. Затем вертикально реализуется System Context через порт и in-memory adapter.
3. После этого добавляется точный lookup и все три штатных исхода.
4. Когда доменное поведение стабильно, подключается Git file adapter и реальные
   JSON/Markdown-источники с общим contract suite.
5. Затем добавляются CLI и Make-команды как внешний проверочный срез.
6. В конце обновляется документация и выполняется полная проверка реализации.

Каждая задача после первой зависит от предыдущей. Сетевые и инфраструктурные
зависимости отсутствуют.

## Задача 1. Настроить Python-проект и строгую модель знаний

**Связанные требования:** REQ-009–REQ-014, REQ-026.

**Критерии приёмки:** Pydantic-модели принимают все согласованные валидные
формы, запрещают extra-поля и невалидные locator; `KnowledgeCatalog` выявляет
нарушения ID, глобальной уникальности алиасов и ссылочной целостности.

**Зависимости:** нет.

**Файлы:**

- `backend/pyproject.toml`;
- `backend/uv.lock`;
- `backend/src/smeshariki_ai/rag/models.py`;
- `backend/tests/unit/rag/test_models.py`.

**Действия:**

1. Настроить дистрибутив `smeshariki-ai` для Python 3.12 с `src`-layout,
   Pydantic 2, Pytest и включением JSON/Markdown package data.
2. Создать строгую неизменяемую `SystemContext` и общие модели `SourceRef`,
   `SpeechStyle`, `KnowledgeRecordBase`, `KnowledgeRef`.
3. Создать enum `EntityType`, `AgeGroup` и discriminated union профилей без
   дополнительных предметных полей.
4. Создать request/result-модели для трёх lookup-статусов.
5. Добавить внутренний `KnowledgeCatalog` и model validators для ID, алиасов,
   locator и межсущностных ссылок.
6. Сгенерировать и зафиксировать `uv.lock`.

**Точная проверка:**

```sh
uv run --project backend pytest backend/tests/unit/rag/test_models.py
```

## Задача 2. Реализовать System Context через порт

**Связанные требования:** REQ-001–REQ-008, REQ-022.

**Критерии приёмки:** сервис возвращает точный immutable `SystemContext` через
порт; prompt соответствует одобренному тексту; fake adapter не использует
файловую систему.

**Зависимости:** задача 1.

**Файлы:**

- `backend/src/smeshariki_ai/rag/ports.py`;
- `backend/src/smeshariki_ai/rag/in_memory.py`;
- `backend/src/smeshariki_ai/rag/service.py`;
- `backend/src/smeshariki_ai/rag/data/system_context.md`;
- `backend/tests/unit/rag/test_system_context.py`.

**Действия:**

1. Описать `StructuredKnowledgeStorePort` как `typing.Protocol` с методами из
   спецификации.
2. Реализовать `InMemoryStructuredKnowledgeStore` с заранее переданными
   валидированными моделями.
3. Реализовать `StructuredKnowledgeService.get_system_context()` без знания о
   формате хранения.
4. Добавить Markdown с version marker и дословным смысловым prompt из
   спецификации.
5. Протестировать неизменность, версию, все восемь инвариантов и отсутствие
   обращений к не относящимся к вызову методам порта.

**Точная проверка:**

```sh
uv run --project backend pytest backend/tests/unit/rag/test_system_context.py
```

## Задача 3. Реализовать детерминированный lookup

**Связанные требования:** REQ-015–REQ-021.

**Критерии приёмки:** сервис строго нормализует ключ, применяет OR-фильтр канона,
возвращает три согласованных статуса и формирует стабильный JSON без
эвристического выбора.

**Зависимости:** задача 2.

**Файлы:**

- `backend/src/smeshariki_ai/rag/service.py`;
- `backend/src/smeshariki_ai/rag/in_memory.py`;
- `backend/tests/unit/rag/test_lookup.py`.

**Действия:**

1. Реализовать единственную функцию нормализации `strip → lower → ё/е` и
   использовать её при загрузке и запросе.
2. В `lookup_knowledge` валидировать аргументы через
   `KnowledgeLookupRequest`.
3. Выполнить точное сопоставление и OR-фильтрацию в установленном порядке.
4. Дедуплицировать совпадения и сортировать ambiguous candidates по типу и ID.
5. Покрыть ID, name, alias, пустой/непустой canon filter, `ё/е`, внутренние
   пробелы, пунктуацию, совпадающие имена и повторяемую сериализацию.

**Точная проверка:**

```sh
uv run --project backend pytest backend/tests/unit/rag/test_lookup.py
```

## Задача 4. Подключить Git file adapter и реальные данные

**Связанные требования:** REQ-010–REQ-014, REQ-018, REQ-022, REQ-025.

**Критерии приёмки:** файловый adapter полностью валидирует Markdown и JSON до
готовности, выдаёт то же поведение, что in-memory adapter, а Git-данные позволяют
проверить три типа профиля и три lookup-статуса.

**Зависимости:** задача 3.

**Файлы:**

- `backend/src/smeshariki_ai/rag/git_store.py`;
- `backend/src/smeshariki_ai/rag/data/knowledge.json`;
- `backend/tests/contract/rag/test_store_contract.py`;
- `backend/tests/integration/rag/test_git_store.py`.

**Действия:**

1. Реализовать `GitStructuredKnowledgeStore` с явными входными путями и
   безопасным UTF-8 чтением без изменения файлов.
2. Разобрать version marker Markdown и провалидировать `SystemContext`.
3. Разобрать корневой JSON через `KnowledgeCatalog`; запретить обслуживание
   запросов после любой validation/read ошибки.
4. Добавить минимальные редакционные записи `character`, `location` и
   `artifact`, включая две version-specific записи с общим именем для
   `ambiguous`; все алиасы оставить глобально уникальными.
5. Запустить один parametrized contract suite для in-memory и file adapters.
6. Интеграционно проверить реальные package data и ошибочные временные файлы.

**Точная проверка:**

```sh
uv run --project backend pytest backend/tests/contract/rag/test_store_contract.py backend/tests/integration/rag/test_git_store.py
```

## Задача 5. Добавить публичный Python-фасад, CLI и Make-команды

**Связанные требования:** REQ-001, REQ-016, REQ-019–REQ-026.

**Критерии приёмки:** пакет экспортирует сервисные контракты, `make run`
запускает рабочий CLI, а `make test` запускает все продуктовые тесты и успешно
завершается.

**Зависимости:** задача 4.

**Файлы:**

- `backend/src/smeshariki_ai/rag/__init__.py`;
- `backend/src/smeshariki_ai/rag/__main__.py`;
- `backend/src/smeshariki_ai/rag/cli.py`;
- `backend/tests/integration/rag/test_cli.py`;
- `Makefile`.

**Действия:**

1. Экспортировать модели, `StructuredKnowledgeStorePort` и
   `StructuredKnowledgeService` как стабильный Python API пакета RAG.
2. Собрать production composition root из package-data путей и файлового
   адаптера только в CLI, оставив сервис независимо тестируемым.
3. Реализовать line-oriented CLI через `shlex`: `context`,
   `lookup <entity_type> <quoted key> [canon_variants...]`, `exit`.
4. На старте полностью загрузить данные и вывести JSON ready event. Результаты
   печатать как UTF-8 JSON со стабильным порядком ключей; ошибки данных выводить
   безопасно в stderr и завершать ненулевым кодом.
5. Заменить временную Compose-проверку цели `make run` на запуск CLI через
   `uv run --project backend python -m smeshariki_ai.rag`.
6. Заменить временно падающую цель `make test` на
   `uv run --project backend pytest` и обновить `make help`.
7. Интеграционно проверить интерактивный stdin/stdout, found/not_found/ambiguous,
   quoted key, `exit` и startup validation error.

**Точная проверка:**

```sh
uv run --project backend pytest backend/tests/integration/rag/test_cli.py
make test
```

## Задача 6. Документировать запуск и выполнить итоговую проверку

**Связанные требования:** REQ-023–REQ-026 и все критерии приёмки.

**Критерии приёмки:** пользователь может по документации запустить CLI и
проверить обе операции; документация не обещает функциональность следующих
изменений; полный test suite проходит.

**Зависимости:** задача 5.

**Файлы:**

- `README.md`;
- `backend/README.md`.

**Действия:**

1. Обновить корневое описание фактически работающих `make run` и `make test`.
2. В backend README показать CLI-команды `context`, `lookup` и `exit`, JSON-
   результаты и ограничения базового RAG.
3. Проверить, что frontend и Docker не изменены, секреты не добавлены, а данные
   RAG отслеживаются Git.
4. Выполнить полный набор проверок ниже; автоматические тесты README и структуры
   не создавать.

**Проверка документации ревью:**

```sh
sed -n '1,240p' README.md
sed -n '1,280p' backend/README.md
```

**Точная проверка продукта:**

```sh
make test
```

## Матрица требований

| Требования | Основная задача | Доказательство |
| --- | --- | --- |
| REQ-001–REQ-008 | 2 | Unit-тест System Context и предметное ревью prompt. |
| REQ-009–REQ-014 | 1, 4 | Pydantic unit-тесты и file-adapter integration tests. |
| REQ-015–REQ-021 | 3 | Table-driven lookup tests и стабильная JSON-сериализация. |
| REQ-022 | 2, 4 | Общий contract suite in-memory/file adapters. |
| REQ-023–REQ-025 | 4, 5 | CLI subprocess tests и ручной smoke run. |
| REQ-026 | 1, 5, 6 | Lock-файл, Python 3.12 и успешный `make test`. |

## Итоговая проверка реализации

После завершения всех задач этапа implement:

1. Синхронизировать зафиксированное окружение без изменения lock-файла.
2. Запустить полный набор продуктовых тестов.
3. Проверить CLI реальными командами `context`, `lookup` для трёх статусов и
   `exit`.
4. Проверить, что в diff отсутствуют изменения frontend, Docker, спецификаций
   `rag-retrieval` и `rag-index-evaluation`.
5. Сопоставить фактическое поведение со всеми REQ-001–REQ-026 и критериями
   приёмки утверждённой спецификации.

**Команды:**

```sh
uv sync --project backend --frozen
make test
make run
git status --short
```

После реализации перейти к отдельному этапу `verify` и сохранить доказательства
в `specs/changes/rag-base/verification.md`. До явного одобрения этого плана
производственный код и тесты не создаются.
