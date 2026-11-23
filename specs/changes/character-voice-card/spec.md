# Voice card персонажа

## Цель

Заменить описательный профиль героя на voice card: примеры реплик, «так не
говорит», роль в сюжете и устойчивые динамики. Отделить интересы и предметы от
черт характера, чтобы фантики и морковка не попадали в сказку автоматически.

## Требования

- REQ-001: `CharacterVersion` получает `interests` и необязательный `voice`.
- REQ-002: `voice` содержит `examples`, `never_says`, `story_role`, `dynamics`
  (`with`, `pattern`, `sources`).
- REQ-003: `get_story_canon` отдаёт voice card и не отдаёт `interests`,
  артефакты и локации.
- REQ-004: `lookup_knowledge` отдаёт `interests` в фактической карточке.
- REQ-005: динамики ссылаются на существующего персонажа с общей версией
  канона; самоссылка запрещена.
- REQ-006: миграция `0016` добавляет `interests`, `voice_story_role`,
  `voice_examples`, `voice_never_says` и `rag_character_dynamics`.
- REQ-007: старые пакеты без `voice` и `interests` остаются валидными.

## Сценарии

- Given у Кроша есть voice card, When вызывается `get_story_canon`, Then
  возвращаются примеры реплик, «так не говорит», роль и динамика с Ёжиком.
- Given у Ёжика интересы «фантики» и «кактусы», When вызывается
  `get_story_canon`, Then интересы не возвращаются.
- Given динамика ссылается на себя, When проверяется пакет, Then ошибка
  `self_reference`.

## Технологии и структура

`rag/models.py`, `rag/tables.py`, `rag/postgres_mappers.py`,
`rag/integrity.py`, `rag/lookup.py`, `rag/story_canon.py`,
`rag/tools.py`, миграция `0016`.

## Команды

- `uv run --project backend --locked --no-sync pytest -q backend/tests/unit/rag`
- `make test`, `make lint`

## Тестирование

Unit-тесты voice card, интересов, динамик и миграции; интеграционный контракт
чтения/записи `voice` и `interests`.

## Границы

- Всегда: интересы и предметы остаются в полном каноне.
- Сначала спросить: изменение формата пакетов beyond optional fields.
- Никогда: не отдавать предметы в story-режим.

## Критерии приёмки

- [x] Voice card возвращается инструментом.
- [x] `interests` не попадают в story-режим.
- [x] Миграция и мапперы обновлены.
- [x] `make test` и `make lint` проходят.

## Открытые вопросы

- Нет.
