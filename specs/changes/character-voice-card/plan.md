# План: voice card персонажа

1. Модель и целостность: `CharacterVersion.interests`, `CharacterVoice`,
   `StoryDynamic`, ссылки динамик в `references_of` и `integrity`.
   Проверка: unit-тесты моделей и целостности.
2. Схема: колонки версии, таблица `rag_character_dynamics`, миграция `0016`,
   `tables.py`, `postgres_mappers.py`.
   Проверка: интеграционные тесты схемы и чтения/записи.
3. Read models: `lookup_knowledge` с `interests`, `get_story_canon` с voice.
   Проверка: `pytest backend/tests/unit/rag`.
4. Данные: voice карточки девяти героев, интересы отделены от трейтов.
   Проверка: `python -m smeshariki_ai.rag check data/knowledge`.
5. Документация и SDD.

Итог: `make test`, `make lint`.
