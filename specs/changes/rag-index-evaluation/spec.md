# Index Lifecycle и offline-оценка RAG

## Цель

Создать отчуждаемый внутренний компонент жизненного цикла BM25-индекса:
атомарно собирать локальный артефакт из вручную подготовленного Git-корпуса,
проверять staged-версию на версионируемом Golden Dataset и активировать её
только после полной валидации и прохождения quality gate `MRR@5 > 0.6`.

Компонент должен одинаково вызываться отдельной backend-командой в CI/CD и при
старте backend, сохранять прежнюю активную версию при любой ошибке и выдавать
воспроизводимые `IndexingReport` и `BenchmarkReport`. Реализация поискового
ранжирования и справочные профили не входят в это изменение: они доступны
только через описанные здесь порты.

## Допущения

- Исходный корпус вручную поддерживается в Markdown-файлах в Git; JSON manifest
  хранит версии, метаданные, устойчивые document ID и пути.
- Golden Dataset вручную поддерживается в JSON в Git.
- Устойчивость ID обеспечивается обязательным code review изменений корпуса.
- Производный индекс хранится локально как `.pkl`, не коммитится и никогда не
  загружается из недоверенного источника.
- Стадия разбиения документов использует контракт, реализованный владельцем
  текстового pipeline; данная спецификация проверяет результат, но не определяет
  внутренний алгоритм разбиения или ранжирования.
- `candidate_k=20`, `K=5`, а порог активации строго больше 0.6 по `MRR@5`.

## Требования

### Снимок корпуса и rebuild

- REQ-001: `CorpusSnapshotRef` должен однозначно задавать `snapshot_id`,
  `corpus_version`, Git revision и SHA-256 checksum manifest и всех входящих
  Markdown-файлов.
- REQ-002: Каждый manifest entry должен содержать устойчивый `document_id`, путь
  к Markdown-файлу, тип источника, язык, метки канона, предметные метаданные и
  `SourceRef` с locator вида `имя_файла:строка` либо `episode_id:timecode`.
- REQ-003: `IndexingService.rebuild(snapshot)` должен получать снимок через
  `CorpusSnapshotSourcePort`, валидировать manifest, каждый документ, уникальность
  ID, ссылки, checksums и результат разбиения до публикации артефакта.
- REQ-004: Любая ошибка одного документа, manifest entry, checksum или chunk
  должна отклонять весь снимок. Частичная индексация запрещена.
- REQ-005: `chunk_id` должен проверяться по единой формуле
  `chunk:<SHA-1(document_id + "\u001f" + ordinal + "\u001f" + chunk_text)>`;
  несовпадение считается ошибкой снимка.
- REQ-006: После полной валидации `IndexingService` должен построить новую
  versioned staging-копию индекса через `IndexBuilderPort`, не изменяя активную
  версию.
- REQ-007: Staging-артефакт должен сохраняться локально как `.pkl` вместе с
  metadata sidecar, содержащим версии корпуса, text processing, builder,
  checksum и время сборки; оба файла считаются одной версией.
- REQ-008: Созданный `.pkl` разрешается загружать только после проверки пути,
  версии и checksum; загрузка произвольного или внешнего pickle запрещена.
- REQ-009: До активации staged-версия должна пройти offline benchmark из этой
  спецификации. Отсутствующий/невалидный Golden Dataset, ошибка evaluation или
  `MRR@5 <= 0.6` запрещают активацию.
- REQ-010: После успешной сборки и quality gate активная версия должна меняться
  одной атомарной операцией `IndexArtifactStorePort.activate`; читатель видит
  либо прежнюю, либо новую полную версию, но не промежуточное состояние.
- REQ-011: При любой ошибке прежняя активная версия и её артефакты остаются
  неизменными и доступными; failed staging не может стать активным.
- REQ-012: Одинаковый `IndexingService.rebuild` должен использоваться backend-
  командой CI/CD и startup hook; если активный индекс с совпадающими версиями и
  checksums уже существует, повторный вызов идемпотентно возвращает статус
  `unchanged`.
- REQ-013: `IndexingReport` должен иметь статус `activated`, `unchanged` или
  `failed` и включать snapshot/index versions, checksums, счётчики документов и
  chunks, предыдущую и итоговую активные версии, benchmark summary и
  машиночитаемые diagnostics.

### Golden Dataset

- REQ-014: Golden Dataset должен содержать от 20 до 30 вручную составленных
  `GoldenQueryCase`, быть связан с конкретной версией корпуса и храниться в Git
  как строго валидируемый JSON.
- REQ-015: Каждый case должен содержать устойчивый ID, непустой query,
  структурированные filters, category, ожидаемо пустой признак и judgments по
  устойчивым `chunk_id`.
- REQ-016: `RelevanceJudgment.grade` должен принимать только 0 или 1, где 0 —
  нерелевантно, 1 — релевантно; иные оценки отклоняют весь Golden Dataset.
- REQ-017: Непустые cases должны покрывать взаимодействия героев, философские
  конфликты, локации/артефакты, версии канона, русские перефразирования и
  морфологические варианты и сложные лексические отрицательные примеры.
- REQ-018: Cases с ожидаемой пустой выдачей должны входить в число 20–30,
  содержать `expected_empty=true`, не иметь grade=1 и проверяться отдельно на
  точное условие `hits == []`.
- REQ-019: Датасет создаётся до release-оценки: запросы формулируются не как
  копии целевых chunks, пул дополняется предметным экспертом, а каждое изменение
  cases, judgments или guideline создаёт новую версию.
- REQ-020: Evaluation cases не должны добавляться в корпус; подбор параметров не
  должен выполняться по итоговому release-набору.

### Offline benchmark и quality gate

- REQ-021: Benchmark должен запрашивать через `RetrievalEvaluationPort` отдельно
  BM25-кандидатов и итоговые hits staged-версии, не реализуя внутри себя поиск.
- REQ-022: Для каждого case хотя бы с одним grade=1 должен вычисляться
  `Recall@20` как доля известных релевантных chunk IDs среди первых 20
  BM25-кандидатов; итоговый Recall@20 — macro average по таким cases.
- REQ-023: Для тех же cases должен вычисляться `MRR@5`: reciprocal rank первого
  grade=1 chunk среди первых пяти итоговых hits, либо 0 при отсутствии;
  итоговое значение — arithmetic mean.
- REQ-024: `NDCG@5` должен вычисляться по бинарным grades для первых пяти
  итоговых hits: `DCG = sum(grade / log2(rank + 1))`, `NDCG = DCG / IDCG`, где
  IDCG строится идеальной сортировкой тех же judgments; итоговое значение —
  macro average.
- REQ-025: Cases с `expected_empty=true` должны исключаться из Recall@20,
  MRR@5 и NDCG@5 и давать отдельные счётчики `empty_cases_passed` и
  `empty_cases_failed` по условию точного пустого списка.
- REQ-026: Quality gate считается пройденным только при `MRR@5 > 0.6`, отсутствии
  ошибок benchmark и `empty_cases_failed == 0`. Recall@20 и NDCG@5 обязательны
  в отчёте, но отдельных release-порогов в MVP не имеют.
- REQ-027: `BenchmarkReport` должен фиксировать версии Golden Dataset, корпуса,
  staged index, text processing, builder и reranker, значения 20 и 5, все три
  метрики, empty-case counters, число cases и diagnostics.
- REQ-028: Benchmark с одинаковыми входными версиями и детерминированным
  evaluation adapter должен давать побайтно одинаковую JSON-сериализацию отчёта;
  текущее время в `BenchmarkReport` не включается.

### Порты и работоспособность

- REQ-029: Внешние зависимости должны быть закрыты шестью портами:
  `CorpusSnapshotSourcePort`, `DocumentChunkingPort`, `IndexBuilderPort`,
  `IndexArtifactStorePort`, `GoldenDatasetSourcePort` и
  `RetrievalEvaluationPort`.
- REQ-030: Для каждого порта должна существовать детерминированная fake/in-memory
  реализация; unit-тесты не обращаются к реальной файловой системе, Git,
  production index или модели.
- REQ-031: Production file adapters должны читать corpus/Golden данные из Git,
  создавать локальные `.pkl`/metadata files и выполнять атомарную активацию на
  одной файловой системе.
- REQ-032: `make rag-index` должен выполнить rebuild и вывести
  `IndexingReport`; `make rag-benchmark` должен оценить заданную staged/active
  версию и вывести `BenchmarkReport`; failed gate даёт ненулевой код.
- REQ-033: Реализация должна работать на Python 3.12, использовать `uv`,
  проходить `make test` и не требовать сети или Qdrant.

## Pydantic-контракты

Все модели используют strict validation, `extra="forbid"`, непустые строки и
неотрицательные счётчики.

| Модель | Поля и ограничения |
| --- | --- |
| `SourceRef` | `source_id`, `source_version`, `locator`, `checksum` |
| `CorpusSnapshotRef` | `snapshot_id`, `corpus_version`, `git_revision`, `checksum` |
| `CorpusManifestEntry` | `document_id`, `path`, `source_type`, `language`, `episode_id`, tuple-поля `character_ids`, `location_ids`, `artifact_ids`, `themes`, `canon_variants`, `source_ref`, `checksum` |
| `CorpusManifest` | `snapshot: CorpusSnapshotRef`, `documents: tuple[CorpusManifestEntry, ...]`; хотя бы один document |
| `IndexableChunk` | `id`, `document_id`, `ordinal`, `text`, `source_type`, `language`, предметные tuple-метаданные, `canon_variants`, `source_ref`, `chunking_version` |
| `IndexArtifactMetadata` | `index_version`, `corpus_version`, `text_processing_version`, `builder_version`, `index_checksum`, `created_at` |
| `IndexingDiagnostic` | `code`, безопасный `message`, `document_id: str | None` |
| `IndexingReport` | `status: activated | unchanged | failed`, snapshot/index metadata, counters, previous/final active versions, `benchmark: BenchmarkSummary | None`, diagnostics |
| `RelevanceJudgment` | `chunk_id: str`, `grade: Literal[0, 1]` |
| `EvaluationFilters` | tuple-поля `source_types`, `character_ids`, `location_ids`, `artifact_ids`, `episode_ids`, `languages`, `canon_variants`; все по умолчанию пусты |
| `GoldenQueryCase` | `id`, `query`, `filters: EvaluationFilters`, `category`, `expected_empty: bool`, `judgments: tuple[RelevanceJudgment, ...]` |
| `GoldenDataset` | `id`, `version`, `corpus_version`, `annotation_guideline_version`, `cases`; длина cases 20–30 |
| `BenchmarkMetric` | `name: recall | mrr | ndcg`, `cutoff`, `value` в диапазоне 0..1 |
| `BenchmarkSummary` | `mrr_at_5`, `gate_threshold=0.6`, `gate_passed` |
| `BenchmarkReport` | все версии; `candidate_k=20`, `k=5`; metrics; evaluated counts; empty counters; `gate_passed`; diagnostics; timestamp отсутствует |

Сервисная сигнатура:

```text
IndexingService.rebuild(snapshot: CorpusSnapshotRef) -> IndexingReport
```

Штатные отказы валидации и quality gate возвращаются как `status="failed"` с
диагностикой. Непредвиденная невозможность безопасно определить состояние
активной версии поднимает типизированную ошибку и не выполняет активацию.

## Сервисные порты

```text
CorpusSnapshotSourcePort.load(snapshot) -> CorpusManifest, documents
DocumentChunkingPort.chunk(documents) -> sequence[IndexableChunk]
IndexBuilderPort.build_staging(chunks, versions) -> staged artifact metadata
IndexArtifactStorePort.verify(staged metadata) -> bool
IndexArtifactStorePort.activate(staged metadata) -> previous active version
IndexArtifactStorePort.active_metadata() -> metadata | None
GoldenDatasetSourcePort.load(version) -> GoldenDataset
RetrievalEvaluationPort.bm25_candidates(index_version, case, k=20) -> chunk IDs
RetrievalEvaluationPort.final_hits(index_version, case, k=5) -> chunk IDs
```

`IndexArtifactStorePort.activate` реализует атомарную смену active pointer через
операцию замены файла на той же файловой системе. Fake store моделирует ту же
семантику, включая сбой непосредственно перед активацией.

## Сценарии

### Успешная сборка и активация

- Given Git snapshot и Golden Dataset полностью валидны
- And staged-версия получает MRR@5 больше 0.6
- And все expected-empty cases возвращают `hits == []`
- When backend-команда вызывает `IndexingService.rebuild`
- Then локальный `.pkl` и metadata sidecar полностью создаются в staging
- And active pointer атомарно переключается на новую версию
- And отчёт имеет статус `activated`

### Атомарный отказ снимка

- Given один Markdown-документ имеет неверный ID, metadata или checksum
- When выполняется rebuild
- Then весь снимок отклоняется
- And builder и activate не вызываются
- And прежняя активная версия не изменяется

### Сбой сборки или активации

- Given полностью валидный снимок
- When builder либо атомарная активация завершается ошибкой
- Then новая версия не становится активной
- And прежняя версия остаётся читаемой
- And диагностика различает стадию отказа

### Непройденный quality gate

- Given staged-индекс имеет MRR@5 ровно 0.6 или меньше
- When выполняется benchmark
- Then gate не пройден из-за строгого условия `> 0.6`
- And staged-версия не активируется

### Пустые запросы Golden Dataset

- Given case имеет `expected_empty=true`
- When evaluation возвращает пустой список
- Then увеличивается `empty_cases_passed`
- And case не входит в Recall, MRR или NDCG

### Идемпотентный rebuild

- Given активная версия совпадает по corpus, processing, builder versions и
  checksums
- When rebuild запущен повторно
- Then повторная сборка и benchmark не выполняются
- And отчёт имеет статус `unchanged`

## Методология Golden Dataset

1. Зафиксировать corpus version и annotation guideline.
2. Вручную составить 20–30 запросов по категориям REQ-017 и REQ-018, не копируя
   дословно целевые фрагменты.
3. Собрать пул кандидатов и дополнить его релевантными chunks, найденными
   предметным экспертом, чтобы уменьшить pooling bias.
4. Разметить каждую пару только 0 или 1 и провести предметное code review.
5. Зафиксировать filters и устойчивые chunk IDs в JSON.
6. Изменять версию при любом изменении queries, judgments или guideline.
7. Не использовать release cases для подбора параметров.

## Технологии и структура

- Python 3.12, Pydantic, Pytest и `uv`.
- Corpus Markdown, manifest JSON и Golden Dataset JSON хранятся в Git.
- Производные index artifacts — локальные `.pkl` плюс JSON metadata, вне Git.
- Сборка запускается в CI/CD или startup hook одной backend-командой.
- Атомарность обеспечивается staging и atomic replace active pointer.
- Все интеграции изолированы портами; сетевые сервисы не нужны.

## Команды

- Сборка/активация: `make rag-index`.
- Отдельная оценка: `make rag-benchmark`.
- Тесты: `make test`.
- `make run` при отсутствии актуального индекса вызывает тот же startup rebuild
  до запуска остальной части backend.

## Тестирование

| Требования | Способ проверки |
| --- | --- |
| REQ-001–REQ-005 | Unit-тест Pydantic manifest, locator, checksums, уникальности ID и SHA-1 chunk ID; один дефект отклоняет snapshot. |
| REQ-006–REQ-013 | State-machine unit-тест rebuild с fault injection на каждой стадии; filesystem integration test staging, checksum, atomic replace, rollback и idempotency. |
| REQ-014–REQ-020 | Unit-тест Golden Dataset: 19/20/30/31 cases, только grades 0/1, empty-case invariants и version fields. |
| REQ-021–REQ-028 | Табличные тесты формул Recall@20, MRR@5, NDCG@5, strict `>0.6`, empty counters и детерминированной сериализации. |
| REQ-029–REQ-031 | Общий contract suite production/fake ports и интеграционный тест локальных adapters без сети. |
| REQ-032, REQ-033 | Subprocess smoke-тест обеих Make-команд, startup rebuild и успешный `make test`. |

Автоматические тесты проверяют поведение lifecycle и метрик, а не наличие
служебных файлов или структуру каталогов.

## Границы

- Всегда: валидировать снимок целиком; строить staging; проверять checksum;
  запускать benchmark до активации; сохранять прежнюю активную версию при сбое.
- Сначала спросить: изменить формулу chunk ID, формат артефакта, состав Golden
  Dataset, метрики или строгий release-порог.
- Никогда: публиковать частично валидный снимок, загружать недоверенный pickle,
  активировать MRR@5 <= 0.6 или реализовывать ранжирование внутри lifecycle.

## Трассировка исходной спецификации

Смысл исходных REQ-029–REQ-040 и относящихся к этому компоненту частей
REQ-041–REQ-044 сохранён и конкретизирован решениями Product Owner.

## Критерии приёмки

- [ ] `make rag-index` атомарно активирует только полностью валидный снимок,
  прошедший quality gate.
- [ ] Любая ошибка документа отклоняет весь snapshot и сохраняет прежний index.
- [ ] Артефакт хранится локально как проверяемый `.pkl`, не попадает в Git и не
  принимается из недоверенного источника.
- [ ] Golden Dataset хранится в Git, содержит 20–30 ручных cases и только
  бинарные grades 0/1.
- [ ] Benchmark корректно вычисляет macro Recall@20, MRR@5 и NDCG@5.
- [ ] Expected-empty cases исключены из трёх метрик и отдельно проверены на
  `hits == []`.
- [ ] Активация разрешена только при MRR@5 > 0.6 и отсутствии failed empty cases.
- [ ] CI/CD и startup используют один `IndexingService.rebuild`.
- [ ] Production и fake ports проходят общий contract suite.
- [ ] `make test` успешно проходит на Python 3.12 через `uv` без сети и Qdrant.

## Открытые вопросы

- Нет. Все решения для данного изменения утверждены Product Owner.
