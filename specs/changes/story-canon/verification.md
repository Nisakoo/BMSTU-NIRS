# Проверка: компактный `story-canon`

Дата: 2026-11-23.

Статус: успешно.

## Что проверено

- `StoryCanonLookup` читает существующий `KnowledgeReader` и не меняет схему
  БД.
- `StoryCharacter` содержит только возраст, характер, речь, коронные фразы и
  отношения `to/type`; свободные описания отношений, `sources`, локации и
  артефакты не выходят.
- Для Кроша на реальном пакете `data/knowledge` результат не содержит
  «скамейку» и `description`, хотя в исходном отношении она раньше была.
- `GetStoryCanonTool` зарегистрирован в `ToolRegistry` рядом с
  `lookup_knowledge` и `search_lore`; все три используют общий reader.
- `lookup_knowledge` не менялся и по-прежнему отдаёт полные факты.
- Системный промпт различает `get_story_canon`, `lookup_knowledge` и
  `search_lore` и требует не превращать профиль в сюжет.
- Логи не содержат имён героев и описаний.

## Требования

| Требования | Проверка | Результат |
| --- | --- | --- |
| REQ-001–REQ-003 | `test_story_canon.py`: состав модели, отсутствие `description`, `sources`, локаций и артефактов | Пройдено |
| REQ-004–REQ-008 | `test_story_canon.py`: версия, отсутствие версии, лимит 3, дубли, пустое хранилище | Пройдено |
| REQ-009–REQ-012 | `test_story_canon_tool.py`: JSON, аргументы, `invalid_arguments`, описание | Пройдено |
| REQ-013 | `test_bootstrap.py`: `get_story_canon` в реестре, общий reader, production/in-memory | Пройдено |
| REQ-014 | `test_story_canon.py::test_logs_do_not_contain_character_names` | Пройдено |
| REQ-015–REQ-016 | Ревью diff: миграций нет; `docs/knowledge.md`, `docs/rag.md`, `docs/agent.md`, `docs/README.md`, `AGENTS.md` обновлены | Пройдено |
| REQ-017–REQ-018 | `make lint`, `make test`, `make test-integration`; реальная проверка Кроша | Пройдено |

## Команды и результаты

```text
make lint
All checks passed!
180 files already formatted

make test
937 passed, 133 skipped (backend Pytest)
219 passed (frontend Node)

make test-integration
1070 passed
```

Ручная проверка на реальном пакете:

```text
StoryCanonLookup(data/knowledge).lookup(["Крош"])
status: found
Крош: разговорный, быстрый, восклицательный
отношения: Ёжик/friendship, Ёжик/neighborhood, Бараш/friendship
contains "скамейк": false
contains "description": false
```

`make knowledge-check DIR=data/knowledge`:

```text
Сущностей: continuities: 1, works: 1, episodes: 32, characters: 9, locations: 10, artifacts: 15
Пакет валиден.
```

## Ограничения и отклонения

- `story-canon` отдаёт только персонажей; локации и артефакты для сюжета
  остаются в `lookup_knowledge`.
- Если у героя нет версии в запрошенном `continuity`, версия другого канона
  не подставляется.
- Правка отношения Кроша в `data/knowledge` — изменение данных, а не кода;
  после неё нужен `make knowledge-load` и обновление `encrypted/data.enc`.
- Реальные данные не коммитятся.
- Схема БД и миграции не менялись.

## Критерии приёмки

- [x] `StoryCanon` содержит только возраст, характер, речь, фразы и
      отношения `to/type`.
- [x] Описание отношения со скамейкой не попадает в story-режим.
- [x] `get_story_canon` возвращает компактный JSON и безопасные статусы.
- [x] `lookup_knowledge` по-прежнему отдаёт полные факты.
- [x] Оба инструмента используют один `KnowledgeReader`; БД не меняется.
- [x] Логи не содержат имён героев и описаний.
- [x] Документация и `AGENTS.md` обновлены.
- [x] `make lint`, `make test` и `make test-integration` проходят.
