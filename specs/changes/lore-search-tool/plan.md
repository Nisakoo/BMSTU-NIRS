# План: инструмент `search_lore` с контекстным бюджетом

## Порядок и зависимости

Сначала появляется builder и его лимиты, затем инструмент, после этого
регистрация в bootstrap. Рискованные места — дедупликация по документу,
обрезка по символам и безопасный `unavailable`; они проверяются unit-тестами
до подключения к агенту.

## Задача 1. Контекстный бюджет

**Требования:** REQ-001–REQ-004.

**Критерии:** `LoreContextBuilder` ограничивает 3 фрагментами, одним
фрагментом на документ и 1600 символами; отбрасывает score ниже 0.5 от
лучшего; пустой результат даёт `empty`; score и внутренние id не попадают в
контекст.

**Файлы:** `rag/lore/context.py`,
`backend/tests/unit/rag/lore/test_context.py`.

**Зависимости:** `lore-bm25-core`.

**Проверка:**
`uv run --project backend --locked pytest backend/tests/unit/rag/lore/test_context.py -q`.

## Задача 2. Инструмент `search_lore`

**Требования:** REQ-005–REQ-008, REQ-012.

**Критерии:** `SearchLoreTool` с аргументом `query`; JSON
`{status, passages, message}`; нет score/id; `empty` и `unavailable`
безопасны; описание требует не более одного вызова на сказку и запрещает
пересказ/перечисление фактов; `ToolRegistry` валидирует аргументы.

**Файлы:** `rag/lore/tools.py`,
`backend/tests/unit/rag/lore/test_tool.py`.

**Зависимости:** задача 1.

**Проверка:**
`uv run --project backend --locked pytest backend/tests/unit/rag/lore/test_tool.py -q`.

## Задача 3. Регистрация в bootstrap

**Требования:** REQ-009–REQ-011.

**Критерии:** production `create_application` передаёт `PostgresBm25Index` и
`MorphAnalyzer`; `build_agent_service` принимает необязательные зависимости;
тесты без БД получают пустой `InMemoryBm25Index` и `SimpleAnalyzer`;
`ToolRegistry` содержит `get_context`, `lookup_knowledge`, `search_lore`.

**Файлы:** `bootstrap.py`, `backend/tests/unit/test_bootstrap.py`.

**Зависимости:** задача 2.

**Проверка:**
`uv run --project backend --locked pytest backend/tests/unit/test_bootstrap.py -q`.

## Задача 4. Документация и `AGENTS.md`

**Требования:** REQ-013.

**Критерии:** описаны инструмент, бюджет 3/1600/0.5, правило «ориентир, а не
сюжет», отсутствие score/id и безопасные статусы; общие файлы изменены
аддитивно.

**Файлы:** `docs/lore.md`, `docs/rag.md`, `docs/agent.md`,
`docs/README.md`, `AGENTS.md`.

**Зависимости:** задача 3.

**Проверка:** ревью документации и diff общих файлов.

## Задача 5. Полная проверка изменения

**Требования:** REQ-014.

**Критерии:** unit- и integration-тесты проходят; `search_lore` вызывается
через `ToolRegistry` на синтетическом лоре; логи не содержат текст запроса и
фрагменты.

**Файлы:** `specs/changes/lore-search-tool/verification.md`.

**Зависимости:** задачи 1–4.

**Проверка:** `make lint`, `make test`, `make test-integration`; ручной вызов
`search_lore`.
