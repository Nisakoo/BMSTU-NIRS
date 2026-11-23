# Проверка: voice card персонажа

## Результат

Voice card добавлен в модель знаний и PostgreSQL. `get_story_canon` отдаёт
примеры реплик, «так не говорит», роль и динамики; интересы и предметы в
story-режим не попадают.

## Требования

| Требование | Проверка | Результат |
| --- | --- | --- |
| REQ-001–REQ-002 | `pytest backend/tests/unit/rag/test_story_canon.py` | Пройдено |
| REQ-003 | Voice card в ответе, `interests` отсутствуют | Пройдено |
| REQ-004 | `lookup_knowledge` отдаёт `interests` | Пройдено |
| REQ-005 | Unit-тесты моделей и целостности | Пройдено |
| REQ-006 | Миграция `0016`, `tables.py`, мапперы | Ревью diff; интеграционный тест добавлен |
| REQ-007 | `rag check data/knowledge` | Пакет валиден |

## Команды

```text
uv run --project backend --locked --no-sync pytest -q backend/tests/unit
740 passed
```

```text
uv run --project backend --locked --no-sync python -m smeshariki_ai.rag check data/knowledge
Пакет валиден.
```

## Ограничения

- Интеграционные тесты PostgreSQL не запущены в этой среде: Docker Desktop
  перестал быть доступен из WSL. Тесты чтения/записи voice добавлены в
  `test_reader_contract.py`.
- Примеры реплик и `never_says` — кураторские, а не автоматически извлечённые
  из транскриптов: в сценариях нет разметки говорящего.
