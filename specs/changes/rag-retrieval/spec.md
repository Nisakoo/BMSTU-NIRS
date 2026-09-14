# Retrieval Pipeline MVP: поиск по текстовому лору

## Цель

Создать независимо запускаемый двухступенчатый движок поиска по готовому
текстовому корпусу: лексический отбор кандидатов через `rank_bm25` и точную
пересортировку локальным Cross-Encoder через `sentence-transformers`.
Компонент предоставляет сервис `search_lore_context`, возвращающий до пяти
фрагментов с raw scores и provenance, и может проверяться через отдельную
Make-команду без agent loop и сетевого API.

Компонент получает готовый или переданный корпус и не управляет сборкой,
публикацией, версионированием либо атомарной заменой сохраняемых артефактов.

## Допущения

- Корпус передаётся как валидированная последовательность `LoreDocument` либо
  `LoreChunk` через порт источника.
- Основной язык MVP — русский.
- Cross-Encoder заранее доступен на локальном диске; runtime не скачивает модель
  и не обращается к сети.
- Идентификатор/путь конкретной совместимой Cross-Encoder модели является
  обязательной конфигурацией запуска, а не зашитым vendor-specific значением.
- Термин «семантический поиск» в этом MVP означает Cross-Encoder reranking
  BM25-кандидатов, а не отдельный retrieval-канал или объединение выдач.

## Требования

### Lore-модели и обработка текста

- REQ-001: `LoreDocument` должен быть строгой Pydantic-моделью для источника
  `transcript`, `synopsis` или `situation` с устойчивым ID, текстом, языком,
  предметными метаданными, метками канона и `SourceRef`.
- REQ-002: `SourceRef.locator` должен быть строкой `имя_файла:строка` либо
  `episode_id:timecode`; provenance каждого результата должен однозначно вести
  к документу и фрагменту.
- REQ-003: Текст документа должен разбиваться только по естественным границам
  абзацев, разделённых одной или несколькими пустыми строками. Пустые абзацы
  отбрасываются, порядок сохраняется, overlap и скользящие окна отсутствуют.
- REQ-004: `LoreChunk` должен хранить устойчивый `id`, `document_id`, `ordinal`,
  исходный текст абзаца, символьный `span`, унаследованные метаданные,
  `chunking_version` и `SourceRef`.
- REQ-005: `chunk.id` должен иметь вид `chunk:<sha1-hex>` и вычисляться как SHA-1
  от UTF-8 представления `document_id + "\u001f" + ordinal + "\u001f" +
  chunk_text`; одинаковые входы дают одинаковый ID, изменение любого элемента —
  новый ID. MD5 в MVP не используется.
- REQ-006: Нормализация запроса и chunks для BM25 должна выполняться одинаково:
  `strip`, lower case, замена `ё` на `е`, удаление Unicode-пунктуации,
  разделение по whitespace и Snowball stemming для русского языка из NLTK.
  Пунктуацией считается символ, чья Unicode category начинается с `P`;
  стоп-слова в MVP не удаляются.
- REQ-007: Исходный текст в `LoreChunk` и выдаче не должен заменяться
  нормализованным; нормализованные токены используются только внутри BM25.

### Фильтрация и двухступенчатый поиск

- REQ-008: `search_lore_context(query, filters, top_k=5)` должен валидировать
  аргументы как `LoreSearchRequest` и возвращать `LoreSearchResult`.
- REQ-009: Пустой после `strip` query, query без токенов после нормализации и
  `top_k < 1` должны отклоняться до вызова поисковых адаптеров; значение `top_k`
  по умолчанию равно 5.
- REQ-010: Поддерживаются фильтры по `source_types`, `character_ids`,
  `location_ids`, `artifact_ids`, `episode_ids`, `languages` и
  `canon_variants`; пустое поле фильтра не ограничивает выдачу.
- REQ-011: Несколько значений внутри одного поля объединяются OR, непустые поля
  между собой — AND. Если chunk не имеет хотя бы одной запрошенной метки
  непустого поля, он строго исключается.
- REQ-012: Фильтры должны применяться до BM25, без LLM и без изменения raw text.
- REQ-013: BM25 candidate retrieval должен использовать pure Python библиотеку
  `rank_bm25` и конфигурацию `candidate_k=20` по умолчанию.
- REQ-014: Эффективное число кандидатов вычисляется как
  `max(configured_candidate_k, top_k)`; поэтому BM25 никогда не возвращает
  reranker меньше кандидатов, чем запрошенный размер ответа, если столько
  отфильтрованных chunks существует.
- REQ-015: Только BM25-кандидаты должны передаваться локальному Cross-Encoder,
  реализованному через `sentence-transformers`; итоговая сортировка выполняется
  по raw Cross-Encoder score по убыванию.
- REQ-016: При одинаковом Cross-Encoder score tie-break выполняется по raw BM25
  score по убыванию, затем по `chunk.id` по возрастанию.
- REQ-017: Результат должен содержать не более `top_k` hits, ранги начиная с 1,
  исходные chunks, raw BM25 и Cross-Encoder scores и полный provenance.
- REQ-018: Raw scores возвращаются без нормализации и не объявляются
  вероятностями; ответ фиксирует версии text processing и reranker.
- REQ-019: Если ни один chunk не прошёл фильтры или BM25 не вернул кандидатов,
  сервис должен успешно вернуть `hits: []` и не вызывать Cross-Encoder с пустым
  списком.
- REQ-020: Любая ошибка загрузки/вызова Cross-Encoder должна немедленно завершать
  запрос типизированной ошибкой `reranker_failed`; fallback на BM25-порядок и
  частичная выдача запрещены.
- REQ-021: Ошибки корпуса и BM25 должны отличаться от штатной пустой выдачи и
  возвращаться как типизированные fail-fast ошибки.
- REQ-022: Embeddings, Qdrant, векторный retrieval и объединение нескольких
  retrieval-каналов в MVP запрещены.

### Порты и работоспособность

- REQ-023: Внешние зависимости должны быть закрыты тремя портами:
  `LoreCorpusPort`, `BM25SearchPort` и `RerankerPort`; доменный pipeline не
  зависит от API конкретных библиотек и файлов.
- REQ-024: Production adapters должны использовать `rank_bm25` и локальный
  `sentence-transformers`, а unit-тесты — детерминированные in-memory/fake
  реализации всех трёх портов.
- REQ-025: Один contract suite должен проверять совместимое поведение production
  и fake adapters, включая порядок ID, количество scores и ошибки.
- REQ-026: `make rag-search QUERY="..."` должен выполнить поиск по переданному
  или fixture-корпусу и вывести `LoreSearchResult` как UTF-8 JSON; ошибка
  reranker должна приводить к ненулевому коду процесса.
- REQ-027: Реализация должна работать на Python 3.12, управлять зависимостями
  через `uv` и проходить `make test` без сети и Qdrant.

## Pydantic-контракты

Все модели используют strict validation, `extra="forbid"`, непустые
обязательные строки и стабильный порядок tuple-полей.

| Модель | Поля и ограничения |
| --- | --- |
| `SourceRef` | `source_id`, `source_version`, `locator`, `checksum`: непустые строки |
| `LoreDocument` | `id`, `title`, `text`, `language`; `source_type: transcript | synopsis | situation`; `episode_id: str | None`; tuple-поля `character_ids`, `location_ids`, `artifact_ids`, `themes`, `canon_variants`; `source_ref` |
| `TextSpan` | `start: int >= 0`, `end: int > start`; полуинтервал исходного текста |
| `LoreChunk` | `id`, `document_id`, `ordinal >= 0`, `text`, `span`, `source_type`, `document_title`, `episode_id`, tuple-поля `character_ids`, `location_ids`, `artifact_ids`, `themes`, `canon_variants`, `language`, `chunking_version`, `source_ref` |
| `LoreFilters` | семь tuple-полей из REQ-010; по умолчанию все пусты |
| `LoreSearchRequest` | `query: str`, `filters: LoreFilters = LoreFilters()`, `top_k: int = 5`, `top_k >= 1` |
| `BM25Candidate` | `chunk: LoreChunk`, `bm25_score: float` |
| `RerankerScore` | `chunk_id: str`, `score: float`; ровно один результат на переданный chunk |
| `LoreProvenance` | `source_ref`, `document_id`, `document_title`, `episode_id`, `chunk_id`, `span` |
| `LoreSearchHit` | `rank >= 1`, `chunk`, `bm25_score`, `reranker_score`, `provenance` |
| `RetrievalVersions` | `corpus_version`, `text_processing_version`, `reranker_version` |
| `LoreSearchResult` | `query`, применённые `filters`, `hits`, `versions` |
| `RetrievalError` | `code: corpus_failed | bm25_failed | reranker_failed | inconsistent_adapter_result`, безопасный `message` |

Сервисная сигнатура:

```text
search_lore_context(
    query: str,
    filters: LoreFilters = LoreFilters(),
    top_k: int = 5,
) -> LoreSearchResult
```

## Алгоритм

1. Провалидировать `LoreSearchRequest`.
2. Получить готовые документы через `LoreCorpusPort` и детерминированно разбить
   их по абзацам в `LoreChunk`.
3. Применить AND/OR-фильтры к chunks.
4. Если множество пусто, вернуть `hits: []`.
5. Нормализовать query и отфильтрованные chunks по REQ-006.
6. Получить через `rank_bm25` первые
   `max(candidate_k=20, top_k)` кандидатов.
7. Передать пары `query + raw chunk text` локальному Cross-Encoder.
8. Проверить полноту и уникальность ответов reranker; при нарушении завершиться
   ошибкой.
9. Отсортировать по Cross-Encoder score, BM25 score и chunk ID.
10. Вернуть первые `top_k` hits с raw scores и provenance.

## Сервисные порты

```text
LoreCorpusPort.documents() -> sequence[LoreDocument]
LoreCorpusPort.version() -> str

BM25SearchPort.search(
    normalized_query_tokens,
    filtered_chunks,
    candidate_k,
) -> sequence[BM25Candidate]

RerankerPort.rerank(
    raw_query,
    candidate_chunks,
) -> sequence[RerankerScore]
RerankerPort.version() -> str
```

Production `RerankerPort` загружает модель только с локального пути и работает
в offline mode. Отсутствующий путь или несовместимая модель являются ошибкой
инициализации.

## Сценарии

### Обычный поиск

- Given готовый корпус содержит больше двадцати подходящих chunks
- When вызван `search_lore_context` с параметрами по умолчанию
- Then BM25 выбирает 20 кандидатов
- And Cross-Encoder пересортировывает эти 20 кандидатов
- And возвращаются первые 5 hits с raw scores и provenance

### Комбинация фильтров

- Given фильтр содержит двух персонажей и один язык
- When выполняется поиск
- Then chunk проходит поле персонажей при совпадении любого из двух ID
- And одновременно обязан совпасть с языком
- And chunk без language metadata отсекается

### top_k больше candidate_k

- Given configured candidate_k равен 20
- When вызван поиск с top_k равным 25
- Then effective candidate_k равен 25
- And pipeline не уменьшает top_k скрытым лимитом кандидатов

### Пустая выдача

- Given строгие фильтры исключили все chunks
- When выполняется поиск
- Then возвращается успешный результат с `hits: []`
- And reranker не вызывается

### Сбой reranker

- Given BM25 вернул кандидатов
- When локальный Cross-Encoder завершился ошибкой
- Then сервис возвращает `reranker_failed`
- And не возвращает BM25-кандидатов как итоговый ответ

### Стабильный chunk ID

- Given одинаковые document ID, ordinal и raw text
- When chunking выполняется повторно
- Then получается одинаковый SHA-1 chunk ID
- And overlap отсутствует

## Технологии и структура

- Python 3.12, Pydantic, Pytest и `uv`.
- `rank_bm25` — единственный BM25 adapter MVP.
- `nltk.stem.snowball.SnowballStemmer("russian")` — стемминг.
- `sentence-transformers` CrossEncoder — локальный reranker.
- Production adapters изолированы портами; unit-тесты используют fakes.
- Компонент остаётся внутренним модулем backend.

## Команды

- Запуск: `RERANKER_MODEL_PATH=/local/model make rag-search QUERY="текст"`.
- Тесты: `make test`.

## Тестирование

| Требования | Способ проверки |
| --- | --- |
| REQ-001–REQ-007 | Unit-тест Pydantic-моделей, paragraph split, отсутствия overlap, SHA-1 fixtures и русской нормализации. |
| REQ-008–REQ-012 | Table-driven unit-тесты validation и всех комбинаций OR/AND/пустых metadata. |
| REQ-013–REQ-019 | Unit-тест pipeline с fake adapters и интеграционный тест `rank_bm25`: 20→5, effective candidate_k, raw scores, tie-break, provenance и empty result. |
| REQ-020–REQ-022 | Fault-injection тесты каждого fail-fast пути и проверка отсутствия fallback/запрещённых backend-вызовов. |
| REQ-023–REQ-025 | Общий contract suite для production и fake adapters. |
| REQ-026, REQ-027 | Subprocess smoke-тест Make-команды и успешный `make test` без сети. |

Тесты проверяют поведение Python-кода, а не структуру каталогов или наличие
служебных файлов.

## Границы

- Всегда: фильтровать до BM25; применять одинаковую нормализацию; возвращать raw
  scores и provenance; завершаться fail-fast при ошибке reranker.
- Сначала спросить: изменить зафиксированные формулы ID, фильтры, значения K,
  обработку текста или библиотеки.
- Никогда: скачивать модель во время запроса, обращаться к сети, выполнять
  fallback на BM25 или добавлять иной retrieval-канал в MVP.

## Трассировка исходной спецификации

Смысл исходных REQ-014, REQ-015, REQ-021–REQ-028 и относящихся к этому
компоненту частей REQ-041–REQ-044 сохранён и конкретизирован решениями Product
Owner.

## Критерии приёмки

- [ ] `make rag-search` возвращает валидный JSON для реального `rank_bm25` и
  локального Cross-Encoder.
- [ ] Paragraph chunking не создаёт overlap, а SHA-1 ID воспроизводим.
- [ ] Нормализация использует lower case, `ё`→`е`, удаление пунктуации и русский
  Snowball stemming без удаления стоп-слов.
- [ ] Фильтры выполняют OR внутри поля, AND между полями и строго отбрасывают
  chunks без запрошенной метки.
- [ ] Значения по умолчанию равны top_k=5 и candidate_k=20; effective candidate_k
  никогда не меньше top_k.
- [ ] Выдача содержит исходный текст, raw scores обеих стадий и provenance.
- [ ] Ошибка Cross-Encoder всегда приводит к `reranker_failed` без fallback.
- [ ] Embeddings, Qdrant и векторный retrieval отсутствуют.
- [ ] Production adapters и fakes проходят общий contract suite.
- [ ] `make test` успешно проходит на Python 3.12 через `uv` без сети.

## Открытые вопросы

- Нет. Все решения для данного изменения утверждены Product Owner.
