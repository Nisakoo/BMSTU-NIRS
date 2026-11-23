# Точечные поля lookup_knowledge

## Цель

Сузить `lookup_knowledge` для сказки: запрашивать факт под сцену, а не всю
карточку героя. Инструмент остаётся точным фактическим поиском.

## Требования

- REQ-001: аргументы `lookup_knowledge` получают необязательный `fields`:
  `speech`, `traits`, `relationships`.
- REQ-002: при `fields` карточка персонажа содержит только запрошенные части;
  идентичность (`id`, `name`, `aliases`, `species`, `age_group`,
  `continuities`) остаётся всегда.
- REQ-003: без `fields` поведение прежнее.
- REQ-004: локации, артефакты и эпизоды возвращаются как раньше.
- REQ-005: неверные `fields` дают `invalid_arguments`, хранилище не
  вызывается.
- REQ-006: описание инструмента и системный промпт требуют вызывать его под
  конкретный факт сцены.

## Сценарии

- Given нужна только речь Пина, When `fields=["speech"]`, Then в карточке нет
  трейтов и отношений.
- Given `fields` не указан, Then карточка полная.
- Given `fields=["unknown"]`, Then `invalid_arguments`.

## Технологии и структура

`rag/lookup.py`, `rag/tools.py`, `agent/prompts/system.md`.

## Команды

- `uv run --project backend --locked --no-sync pytest -q backend/tests/unit/rag`
- `make test`, `make lint`

## Тестирование

Unit-тесты `KnowledgeLookup` и `ToolRegistry`, проверка описания инструмента.

## Границы

- Всегда: `lookup_knowledge` остаётся фактическим инструментом.
- Сначала спросить: удаление инструмента или смена его имени.
- Никогда: не удалять полную карточку без `fields`.

## Критерии приёмки

- [x] `fields` работает и валидируется.
- [x] Без `fields` поведение не изменилось.
- [x] `make test` и `make lint` проходят.
