# Проверка: поиск стиля в лоре

## Результат

`search_lore` умеет искать по тегам: `mode=style` оставляет диалоговые
документы, `plot` — сюжетные, `facts` — фактовые, `any` не фильтрует.
Схема БД не менялась: используется существующее поле `tags`.

## Требования

| Требование | Проверка | Результат |
| --- | --- | --- |
| REQ-001–REQ-002 | `pytest backend/tests/unit/rag/lore/test_index.py` | Пройдено |
| REQ-003–REQ-004 | `pytest backend/tests/unit/rag/lore/test_tool.py` | Пройдено |
| REQ-005 | Ревью diff: миграций нет | Пройдено |
| REQ-006 | `lore-check data/lore` | 84 документа, валиден |

## Команды

```text
uv run --project backend --locked --no-sync pytest -q backend/tests/unit/rag/lore
79 passed
```

## Ограничения

- Теги `style`/`dialogue` проставлены эвристически по плотности диалога; это
  стартовая разметка, а не ручная кураторская выборка.
- PostgreSQL-фильтр по тегам покрыт интеграционным тестом, но в этой среде
  не запускался из-за недоступности Docker.
