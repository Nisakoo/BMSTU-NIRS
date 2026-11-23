# План: компактный `story-canon`

## Порядок и зависимости

Сначала read model и проекция, затем инструмент, после этого bootstrap и
промпт. Рискованные места — выбор версии канона, отношения без описаний и
поведение при отсутствии версии; они проверяются на синтетическом
`InMemoryKnowledgeStore` до подключения к агенту.

## Задача 1. Read model и `StoryCanonLookup`

**Требования:** REQ-001–REQ-008.

**Критерии:** `StoryCharacter` содержит только возраст, характер, речь,
фразы и отношения `to/type`; `StoryCanonLookup` читает через
`KnowledgeReader`, выбирает версию по `continuity`, отбрасывает свободные
описания, источники, артефакты и локации; `not_found`/`unavailable`
безопасны; лимит — 3 имени.

**Файлы:** `rag/story_canon.py`,
`backend/tests/unit/rag/test_story_canon.py`.

**Зависимости:** существующие `KnowledgeReader`, `InMemoryKnowledgeStore`.

**Проверка:**
`uv run --project backend --locked pytest backend/tests/unit/rag/test_story_canon.py -q`.

## Задача 2. Инструмент `get_story_canon`

**Требования:** REQ-009–REQ-012.

**Критерии:** аргументы `names` (1–3) и `continuity`; JSON без `description`,
`sources`, локаций и артефактов; `invalid_arguments` для пустых имён и
лишних полей; описание запрещает превращать профиль в сюжет.

**Файлы:** `rag/tools.py`,
`backend/tests/unit/rag/test_story_canon_tool.py`.

**Зависимости:** задача 1.

**Проверка:**
`uv run --project backend --locked pytest backend/tests/unit/rag/test_story_canon_tool.py -q`.

## Задача 3. Bootstrap и промпт

**Требования:** REQ-013–REQ-015.

**Критерии:** production и тестовый bootstrap регистрируют
`get_story_canon` вместе с `lookup_knowledge` и `search_lore`; общий
`KnowledgeReader`; промпт различает три инструмента и запрещает переносить
предметы из профиля в сказку; логи без имён.

**Файлы:** `bootstrap.py`, `agent/prompts/system.md`,
`backend/tests/unit/test_bootstrap.py`,
`backend/tests/unit/agent/test_prompts.py`.

**Зависимости:** задача 2.

**Проверка:**
`uv run --project backend --locked pytest backend/tests/unit/test_bootstrap.py backend/tests/unit/agent/test_prompts.py -q`.

## Задача 4. Документация

**Требования:** REQ-016, REQ-018.

**Критерии:** `docs/knowledge.md` фиксирует правило описаний отношений;
`docs/rag.md`, `docs/agent.md`, `docs/README.md`, `AGENTS.md` описывают
`get_story_canon` и границу с `lookup_knowledge`/`search_lore`; схема БД не
меняется.

**Файлы:** `docs/knowledge.md`, `docs/rag.md`, `docs/agent.md`,
`docs/README.md`, `AGENTS.md`.

**Зависимости:** задача 3.

**Проверка:** ревью документации и diff.

## Задача 5. Полная проверка

**Требования:** REQ-017.

**Критерии:** unit-, bootstrap- и integration-тесты проходят; на реальном
пакете `get_story_canon` для Кроша не содержит «скамейку»; `lookup_knowledge`
по-прежнему отдаёт полные факты.

**Файлы:** `specs/changes/story-canon/verification.md`.

**Зависимости:** задачи 1–4.

**Проверка:** `make lint`, `make test`, `make test-integration`; ручной вызов
`get_story_canon`.
