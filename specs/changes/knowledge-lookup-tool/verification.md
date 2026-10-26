# Verification: инструмент агента `lookup_knowledge`

Дата проверки: 26 октября 2026 года.

## Результат

Изменение `knowledge-lookup-tool` соответствует согласованной спецификации.
Агент получает инструмент `lookup_knowledge`: точный поиск персонажей,
локаций, артефактов и эпизодов по имени, алиасу, названию и slug с
компактными карточками. Изменение `bootstrap.py` согласовано с владельцем
agent. Тесты PostgreSQL выполнены командой `make test-integration`
(PostgreSQL 17.10, Redis 7.4.9) на синтетических данных.

При реализации спецификация уточнена: REQ-009 — `reason=not_loaded` при
незагруженных знаниях и поле `match_count` в списке безопасных полей
`observability.py`; REQ-010 — инструмент получает класс `KnowledgeLookup` без
отдельного абстрактного интерфейса.

## Проверка требований

| Требования | Подтверждение | Результат |
| --- | --- | --- |
| REQ-016 | `test_schema.py`: схема совпадает с `tables.metadata`; `0003` → эпизоды без ключа → `0004` заполняет `normalized_title` («  Ёлка  и   ПИН » → «елка и пин»), поиск находит оба эпизода; `downgrade` до `0003` удаляет колонку; пустой ключ отклоняется `CHECK`; контрактные тесты хранилища пишут ключ при загрузке | Пройдено |
| REQ-001, REQ-002 | `test_reader_contract.py` на in-memory и PostgreSQL: имя, алиас, slug, регистр, пробелы, «ё», названия ссылок, эпизод с произведением, произведения и варианты канона не ищутся, один ключ у персонажа, локации и двух эпизодов, нет совпадений, `has_knowledge` | Пройдено |
| REQ-003 | `test_postgres_store.py`: число запросов поиска одинаково при 2 и 50 персонажах; первый оператор — `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY`, `pg_advisory` не используется | Пройдено |
| REQ-004, REQ-014 | Без таблиц `rag_*` — `KnowledgeSchemaNotReadyError`, недоступная БД — `KnowledgeStoreUnavailableError` без адреса в тексте, повреждённые строки — `KnowledgeDataInvalidError`; use case превращает их в `unavailable` | Пройдено |
| REQ-005–REQ-008, REQ-017 | `test_lookup.py`: полные карточки персонажа, локации, артефакта и эпизода с именами вместо slug и без `sources`; порядок по типу и `id`; лимит 10, `total`, `truncated`; `not_found`; `unavailable` для пустого хранилища и ошибок порта; прочие ошибки не скрываются | Пройдено |
| REQ-009 | `caplog`: `rag.lookup.completed` с `outcome`, `match_count`, `started_at`, `duration_ms`; `WARNING` и `error_type` при ошибке хранилища; `reason=not_loaded`; текста запроса и знаний в журнале нет | Пройдено |
| REQ-010–REQ-012 | `test_lookup_tool.py` через `ToolRegistry`: определение и JSON Schema (`name`, `maxLength` 200, без лишних полей), JSON-выход с псевдонимом `from`, пояснения `not_found`/`unavailable`; пустое, длинное, отсутствующее имя и лишнее поле дают `invalid_arguments` без вызова хранилища | Пройдено |
| REQ-013, REQ-014 | `test_bootstrap.py`: реестр — `get_context`, `lookup_knowledge`; production-приложение использует `PostgresKnowledgeStore` на engine истории; явный `auth_service` и `build_agent_service` по умолчанию — `InMemoryKnowledgeStore`, вызов инструмента даёт `unavailable` | Пройдено |
| REQ-015 | Ревью `docs/rag.md`, `docs/knowledge.md`, `docs/logging.md`, `docs/database.md`, `docs/README.md`, `AGENTS.md`. Общие файлы — только добавления, кроме согласованных замен: «RAG и его инструменты» → «поиск по лору RAG» в `docs/README.md` и строка RAG в `docs/database.md` («миграции `0003` и `0004`») | Пройдено |

## Выполненные команды

```text
make lint
All checks passed!; 135 files already formatted

make test
frontend: pass 103, fail 0
backend: 620 passed, 84 skipped (PostgreSQL- и Redis-тесты без переменных)

make test-integration
704 passed in 348.49s
```

Во время прогона доступная память не опускалась ниже 4,1 ГБ, свободное место
на C: не изменилось (62 ГБ), ресурсов проекта `smeshariki-ai-test` не
осталось.

## Ограничения

- Ответ модели с реальной LLM не проверялся: `FakeLLMProvider` не вызывает
  инструменты. Ручное испытание — загрузка пакета знаний, `make run` и чат.
- В `AGENTS.md` (раздел «Реализованные диалоги и HTTP API», п. 11) осталась
  устаревшая ещё до изменения фраза о «пустом `ToolRegistry`»; это раздел
  владельца agent, правка вынесена ему на решение.
