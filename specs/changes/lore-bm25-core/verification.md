# Проверка: BM25-поиск по лору

Дата: 2026-11-22.

Статус: успешно.

## Что проверено

- Собственный BM25 реализован по формуле методички: IDF, `tf`, нормализация
  по длине, `k1=1.2`, `b=0.75`.
- `SimpleAnalyzer` и `MorphAnalyzer` (`pymorphy3`) дают единый контракт
  `terms`; запрос и документы проходят один анализатор.
- YAML-пакет лора проверяется без БД, загружается атомарно и заменяет
  предыдущий корпус.
- Production-поиск работает через PostgreSQL: postings и статистика лежат в
  `rag_lore_*`, BM25 считается одним set-based SQL-запросом; корпус не
  загружается в память backend.
- `InMemoryBm25Index` и `PostgresBm25Index` дают одинаковый порядок на
  контрактном наборе.
- `lore-check`, `lore-load`, `lore-search` и Make-цели работают с кодами
  `0/1/2`; JSON-вывод пригоден для машинной обработки.
- События `lore.load.completed` и `lore.search.completed` не содержат текста
  запросов, документов и термов.
- Миграция `0013_lore_bm25` создаёт шесть таблиц `rag_lore_*`, обратима и не
  связана внешними ключами с другими модулями.

## Требования

| Требования | Проверка | Результат |
| --- | --- | --- |
| REQ-001–REQ-003 | `test_bm25.py`: IDF, насыщение `tf`, длина, пустой корпус, tie-break, дедупликация запроса | Пройдено |
| REQ-004–REQ-005 | `test_analyzer.py`: NFC, `ё → е`, дефисные имена, лемматизация, неизвестные слова | Пройдено |
| REQ-006–REQ-009 | `test_index.py`, `test_services.py`, `test_lore_postgres.py`: in-memory и PostgreSQL, одинаковый порядок | Пройдено |
| REQ-010–REQ-014 | `test_lore_schema.py`, `test_lore_postgres.py`: миграция, замена корпуса, версия, фиксированное число запросов | Пройдено |
| REQ-015–REQ-017 | `test_lore_package.py`, `test_chunking.py`: manifest, поля, id, лишние файлы, симлинки, размеры чанков | Пройдено |
| REQ-018–REQ-019 | `test_lore_cli.py`, ручной запуск `lore-check`, `lore-load`, `lore-search` | Пройдено |
| REQ-020 | `test_services.py::test_lore_events_do_not_log_text`; безопасные поля в `_SAFE_FIELDS` | Пройдено |
| REQ-021 | Ревью `docs/lore.md`, `docs/rag.md`, `docs/database.md`, `docs/README.md` | Пройдено |
| REQ-022 | `make lint`, `make test`, `make test-integration` | Пройдено |

## Команды и результаты

```text
make lint
All checks passed!
172 files already formatted

npm --prefix frontend test
219 passed, 0 failed

make test
884 passed, 132 skipped (backend Pytest)
219 passed (frontend Node)

make test-integration
1016 passed
```

Интеграционный набор включает PostgreSQL 17 и Redis 7 в отдельном
Compose-проекте `smeshariki-ai-test`. Полный RAG-набор отдельно:

```text
make test-integration PYTEST_ARGS="backend/tests/integration/rag -q"
120 passed
```

Ручная проверка CLI на синтетическом пакете:

```text
make lore-check DIR=/tmp/opencode/lore-smoke
Документов: 1
Пакет лора валиден.

python -m smeshariki_ai.rag lore-load /tmp/opencode/lore-smoke
Загрузка 1 выполнена.
Документов: 1, чанков: 1, термов: 11.

python -m smeshariki_ai.rag lore-search "возврат оплаты" --top-k 3
1. [d01/0] Возврат оплаты — 0.575
При оплате картой деньги возвращают на карту. Возврат билета возможен в кассе.
```

JSON-вывод `lore-search` содержит `chunk_id`, `document_id`, `position`,
`title`, `source`, `text`, `score`, `rank`, `total` и `version`.

## Ограничения и отклонения

- `make test` в текущей оболочке требует Node 24: PATH по умолчанию указывал
  на Windows Node 18 и не мог запустить тесты из WSL-пути. Frontend-тесты
  выполнены через nvm Node 24; код frontend не менялся.
- BM25 остаётся лексическим поиском: синонимы и перефразирования не
  гарантируются. Embeddings/`pgvector` в это изменение не входят.
- Инструмент агента `search_lore` и benchmark 30/10/5 не входят в это
  изменение; они запланированы следующими спецификациями.
- Загрузка заменяет корпус целиком; инкрементальная загрузка не реализована.
- Реальные данные не проверялись: в репозитории их нет, тесты используют
  синтетические пакеты. `data/` не коммитится.
- В `observability._SAFE_FIELDS` добавлены аддитивные безопасные поля
  `document_count`, `chunk_count`, `term_count`, `index_version`. Это
  единственное изменение общего backend-модуля; поведения логирования оно не
  меняет.
- `Makefile` получил только аддитивные RAG-цели; `docs/README.md`,
  `docs/rag.md` и `docs/database.md` — RAG-строки и ссылки.
- `bootstrap.py`, `config.py`, `agent`, `application`, `api`, `dialogs`,
  `auth`, `admin` и frontend не изменялись.

## Критерии приёмки

- [x] BM25 реализован самостоятельно и совпадает с формулой методички.
- [x] Production-поиск работает через PostgreSQL и не загружает корпус в
      память; in-memory адаптер проходит тот же контракт.
- [x] YAML-пакет лора проверяется, загружается и заменяет корпус атомарно.
- [x] `lore-check`, `lore-load`, `lore-search` и Make-цели работают с
      кодами `0/1/2`.
- [x] Схема `rag_lore_*` создаётся миграцией `0013` и не связана с другими
      модулями.
- [x] Логи не содержат текста запросов, документов и термов.
- [x] `make lint`, `make test` и `make test-integration` проходят.
- [x] Документация обновлена; `bootstrap.py`, `config.py` и чужие модули не
      изменены.
