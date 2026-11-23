# Проверка: инструмент `search_lore` с контекстным бюджетом

Дата: 2026-11-23.

Статус: успешно.

## Что проверено

- `LoreContextBuilder` оставляет не более 3 фрагментов, не более одного на
  документ и не более 1600 символов; слабые совпадения ниже `0.5` от лучшего
  score отбрасываются.
- `SearchLoreTool` возвращает JSON `{status, passages, message}`; score,
  `document_id`, `chunk_id` и `position` наружу не попадают.
- Пустой и недоступный лор дают безопасные `empty`/`unavailable`, а не
  исключения.
- Production bootstrap регистрирует `search_lore` рядом с `get_context` и
  `lookup_knowledge`, использует `PostgresBm25Index` и `MorphAnalyzer`; тесты
  без БД получают пустой `InMemoryBm25Index` и `SimpleAnalyzer`.
- Описание инструмента требует не более одного вызова на сказку, запрещает
  пересказ и перечисление фактов и просит продолжать по идее пользователя при
  `empty`/`unavailable`.
- Логи не содержат текст запроса, фрагменты и названия документов.

## Требования

| Требования | Проверка | Результат |
| --- | --- | --- |
| REQ-001–REQ-004 | `test_context.py`: лимиты 3/1600, один документ, порог, обрезка, пустой результат | Пройдено |
| REQ-005–REQ-008 | `test_tool.py`: JSON, отсутствие score/id, `empty`, `unavailable`, описание, `ToolRegistry` | Пройдено |
| REQ-009–REQ-011 | `test_bootstrap.py`: `search_lore` в реестре, production/in-memory адаптеры | Пройдено |
| REQ-012 | `test_lore_events_do_not_log_text`; безопасные поля `SearchLore` | Пройдено |
| REQ-013 | Ревью `docs/lore.md`, `docs/rag.md`, `docs/agent.md`, `docs/README.md`, `AGENTS.md` | Пройдено |
| REQ-014 | `make lint`, `make test`, `make test-integration` | Пройдено |

## Команды и результаты

```text
make lint
All checks passed!
179 files already formatted

make test
923 passed, 133 skipped (backend Pytest)
219 passed (frontend Node)

make test-integration
1056 passed
```

Интеграционный тест `search_lore` с PostgreSQL прошёл:
`test_search_lore_tool_uses_postgres_and_returns_compact_context`.

## Ограничения и отклонения

- Системный промпт и `Agent` не менялись; правила использования инструмента
  заданы его описанием. Если модель будет игнорировать инструмент или
  пересказывать фрагменты, потребуется отдельное изменение промпта и
  story-quality.
- Контекстный бюджет фиксирован: 3 фрагмента, 1600 символов, порог 0.5.
- Benchmark и `story canon` в это изменение не входят.

## Критерии приёмки

- [x] `LoreContextBuilder` соблюдает лимиты 3/1600/один документ и порог.
- [x] `search_lore` возвращает компактный JSON без score и внутренних id.
- [x] Пустой и недоступный лор дают безопасные статусы.
- [x] Production bootstrap регистрирует инструмент с PostgreSQL и
      `MorphAnalyzer`; тесты не требуют БД.
- [x] Логи не содержат текст запроса и фрагменты.
- [x] Документация и `AGENTS.md` обновлены.
- [x] `make lint`, `make test` и `make test-integration` проходят.
