# Поиск стиля в лоре

## Цель

Научить `search_lore` искать не только факты, но и примеры диалогов и
сюжетных ходов. Использовать существующее поле `tags` документов лора, не
меняя схему БД.

## Требования

- REQ-001: `LoreQuery` получает необязательные `tags`.
- REQ-002: `LoreIndex.search` принимает `tags`; in-memory и PostgreSQL
  фильтруют документы до ранжирования.
- REQ-003: `search_lore` принимает `mode` (`any`, `style`, `plot`, `facts`).
- REQ-004: `style` ищет документы с тегами `style`/`dialogue`, `plot` — с
  `plot`, `facts` — с `facts`, `any` не фильтрует.
- REQ-005: схема БД и миграции не меняются.
- REQ-006: документы лора получают теги `plot` и выборочно
  `style`/`dialogue`.

## Сценарии

- Given документ с тегом `style`, When `mode=style`, Then он участвует в
  поиске, а документ без тега — нет.
- Given `mode=any`, When выполняется поиск, Then фильтра по тегам нет.

## Технологии и структура

`rag/lore/models.py`, `rag/lore/ports.py`, `rag/lore/index.py`,
`rag/lore/postgres.py`, `rag/lore/services.py`, `rag/lore/tools.py`,
`data/lore`.

## Команды

- `uv run --project backend --locked --no-sync pytest -q backend/tests/unit/rag/lore`
- `make test`, `make lint`

## Тестирование

Unit-тесты фильтра тегов в in-memory индексе и инструменте; интеграционный
тест PostgreSQL-поиска с тегами.

## Границы

- Всегда: теги — существующее поле документа.
- Сначала спросить: изменение формата лора.
- Никогда: не добавлять отдельную БД или embeddings в это изменение.

## Критерии приёмки

- [x] `mode` работает и документирован.
- [x] PostgreSQL и in-memory фильтруют одинаково.
- [x] `make test` и `make lint` проходят.
