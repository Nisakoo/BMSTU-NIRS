# Проверка: voice card персонажа

Исторический оригинал: `git show 5af56b5:specs/changes/character-voice-card/verification.md`.

## Результат

- Voice card добавлен в модель знаний и PostgreSQL. `get_story_canon` отдаёт примеры реплик, «так не говорит», роль и динамики; интересы и предметы в story-режим не попадают.
- 740 passed
- Интеграционные тесты PostgreSQL не запущены в этой среде: Docker Desktop перестал быть доступен из WSL. Тесты чтения/записи voice добавлены в `test_reader_contract.py`.
- Примеры реплик и `never_says` — кураторские, а не автоматически извлечённые из транскриптов: в сценариях нет разметки говорящего.
