# Проверка: точность контекста RAG для сказки

## Результат

Изменение реализовано и проверено. Относительный порог заменён абсолютным
`min_score`, запрос из одних имён даёт пустой контекст, профиль героя больше
не содержит предметов из трейтов.

## Требования

| Требование | Проверка | Результат |
| --- | --- | --- |
| REQ-001–REQ-004 | `pytest backend/tests/unit/rag/lore/test_context.py backend/tests/unit/rag/lore/test_tool.py` | Пройдено |
| REQ-005 | `test_tool.py`: `SearchLore.analyze` передаёт термы | Пройдено |
| REQ-006 | `pytest backend/tests/unit/rag/test_story_canon.py` | Пройдено |
| REQ-007 | `pytest backend/tests/integration/rag/test_reader_contract.py` на PostgreSQL и in-memory | Пройдено |
| REQ-008–REQ-009 | Ревью `rag/tools.py`, diff без миграций | Пройдено |

## Команды

```text
uv run --project backend --locked --no-sync pytest backend -q
1025 passed, 137 skipped
```

Интеграционные тесты RAG на временных PostgreSQL и Redis:

```text
pytest backend/tests/integration/rag
126 passed
```

`make test` не запускается без скачивания `torch` из `download.pytorch.org`;
локальный запуск выполнен через `uv --no-sync`.

## Ручная проверка на реальном корпусе

```text
Крош Ёжик дружба -> ['Настоящие ценности', 'Скамейка']
Крош            -> empty
Крош и Ёжик     -> empty
```

Профиль Ёжика больше не содержит `коллекционирует фантики`, трейт
`сентиментальный, дорожит старыми вещами` сохранён.

## Ограничения

- `min_score=2.0` подобран на реальном корпусе; при смене корпуса его нужно
  перепроверить benchmark-ом.
- Отсев трейтов работает по каноническим именам артефактов и локаций; трейты
  без прямого имени предмета (например, «выращивает кактусы») сохраняются.
