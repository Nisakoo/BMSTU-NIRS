# Verification: гибридный поиск

## Что проверено

### Этап 1. Бюджет контекста

- `LoreContextBuilder` по умолчанию держит 5 пассажей и 4800 символов,
  `RagConfig.lore_max_passages=5`, `lore_max_chars=4800`.
- Замер на трёх наборах (`k=5`): `Context Recall` golden `0.367 → 0.550`,
  контроль `0.633 → 0.867`, dev `0.667 → 0.967`.
- Окно поиска `k=10` достаточно: `k=10/15/20/30` дают одинаковый контекст.
- Тесты: `test_context.py`, `test_backend_config.py` обновлены под дефолты.

### Этап 2. Заголовок как поле с бустом

- Термы заголовка повторяются в первом чанке, `LoreChunk.length` хранит длину
  текста, поэтому длина чанка не растёт.
- Замер «до/после» на одном движке: `doc Recall@5` golden `0.550 → 0.583`,
  контроль `0.833 → 0.867`, dev `0.900 → 0.967`; MRR не хуже.
- Тесты: `test_title_terms_boost_the_first_chunk_without_lengthening_it`,
  `test_title_boost_touches_only_the_first_chunk`.

### Этап 3. Гибрид BM25 + pgvector

- Порт `EmbeddingProvider`: `embed`, `embed_query`, `model_id`, `dimension`.
- `LocalEmbeddingProvider` (e5-small, 384) лениво импортирует `transformers` и
  бросает `EmbeddingUnavailableError`, если зависимость не установлена.
- `InMemoryDenseIndex` (бенчмарк) и `PostgresDenseIndex` (pgvector) дают одни и
  те же кандидаты; `fuse_hits` сохраняет шкалу BM25, поэтому `min_score`
  продолжает работать.
- При сбое плотной части `SearchLore` пишет `lore.search.degraded` и возвращает
  BM25 (`test_search_degrades_to_bm25_when_dense_fails`).
- Миграция `0017` создаёт `vector` и `rag_lore_embeddings`; `lore-load` с
  включённым `RAG_HYBRID_ENABLED` пишет векторы.
- Замер на контрольном наборе: `Recall@5 0.733 → 0.900`, `Context Recall
  0.867 → 0.900`, MRR `0.900`. На golden set гибрид немного хуже
  (`Context Recall 0.583 → 0.550`), поэтому режим выключен по умолчанию.
- Тесты: `test_embeddings.py` (порт, fake, слияние, откат),
  `test_lore_postgres.py::test_postgres_dense_index_returns_persisted_vectors`.

## Команды

```sh
make test                  # 847 unit-тестов
sh docker/test-integration.sh
make lore-benchmark DIR=... --hybrid --context
```

## Результат

- `make lint` — чисто.
- `make test` — 847 unit-тестов.
- `docker/test-integration.sh` — полный прогон на pgvector-образе: миграции,
  схема `rag_lore_embeddings`, запись векторов и гибридный поиск зелёные.
- Контрольный набор не менялся: гибрид проверен на нём один раз, вес выбран по
  dev-набору (`0.5…0.9` дают одинаковый результат, оставлен `0.7`).
- Ограничение размерности проверяется в конструкторе `PostgresLoreStore`
  (`vector(384)`), поэтому несовпадение модели и колонки падает явно, а не в
  середине транзакции.

## Открытые вопросы

- Гибрид помогает 30-документному набору и вредит golden: включать по умолчанию
  рано, нужно понять, почему (84 документа шумнее, метки golden мягче).
- Модель e5-small занимает ~470 МБ; для контейнера заведён том `hf-cache`.
