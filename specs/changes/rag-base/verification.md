# Проверка: базовый RAG — System Context и Structured Knowledge

## Итог

Статус: **успешно**.

Реализация `rag-base` соответствует утверждённой спецификации и плану.
Обязательная команда `make test` проходит, локальный CLI запускается, Python-
пакет собирается вместе с JSON/Markdown-данными. Отключённых тестов нет.

Дата проверки: 2026-09-14.

## Проверенное окружение

- Python 3.12.3;
- uv 0.12.13;
- Pydantic 2.x и Pytest 9.1.1 из `backend/uv.lock`;
- рабочий каталог: корень репозитория.

## Команды и результаты

### Воспроизводимое окружение

```sh
UV_CACHE_DIR=/tmp/smeshariki-ai-uv-cache UV_LINK_MODE=copy \
  uv sync --project backend --frozen
```

Результат: успешно, проверено 11 зафиксированных пакетов, lock-файл не изменён.

### Полный набор тестов продукта

```sh
make test
```

Результат: успешно, собрано и пройдено 40 тестов:

- 4 contract tests;
- 7 integration tests;
- 29 unit tests;
- failures: 0;
- skipped/xfail: 0.

### Сборка дистрибутива

```sh
UV_CACHE_DIR=/tmp/smeshariki-ai-uv-cache UV_LINK_MODE=copy \
  uv build --project backend \
  --out-dir /tmp/smeshariki-ai-rag-base-verify
```

Результат: успешно созданы sdist и wheel. Проверка содержимого wheel через
`python3 -m zipfile -l` подтвердила наличие модулей RAG и ресурсов:

- `smeshariki_ai/rag/data/system_context.md`;
- `smeshariki_ai/rag/data/knowledge.json`.

### Runtime smoke test

```sh
make run
```

В интерактивном сеансе проверены:

```text
context
lookup character "  ПИН  "
lookup character "Пин" movie
lookup location "мастерская пина"
lookup artifact "Пинолет"
lookup character неизвестный
exit
```

Результат: CLI выдал `ready`, System Context версии `1`, детерминированный
`ambiguous`, три результата `found`, результат `not_found` и завершился с кодом
0. Все ответы являются однострочным UTF-8 JSON.

### Scope и целостность

```sh
git diff --check
git status --short frontend docker
rg -n 'pytest\.mark\.(skip|xfail)|pytest\.skip|@unittest\.skip|skipif' backend/tests
```

Результат: ошибок whitespace нет; frontend и Docker не изменены; маркеры
отключения тестов отсутствуют. Спецификации `rag-retrieval` и
`rag-index-evaluation` во время implement/verify не изменялись.

## Проверка требований

| Требование | Статус | Доказательство |
| --- | --- | --- |
| REQ-001 | PASS | `test_service_returns_stable_context_without_loading_records` подтверждает стабильную immutable-модель и одно чтение через порт; runtime вернул версию 1. |
| REQ-002 | PASS | Реальный Markdown и `test_real_system_context_contains_every_invariant` содержат запрет внешнего злодея и конфликт характеров. |
| REQ-003 | PASS | Тот же integration test проверяет все четыре возрастные группы и девять имён. |
| REQ-004 | PASS | Prompt и тест содержат `speech_style`, акцент Пина и просторечия Копатыча. |
| REQ-005 | PASS | Prompt и тест подтверждают детский сюжет и взрослый философский/ироничный слой. |
| REQ-006 | PASS | Prompt и тест подтверждают светлое понимание и запрет произнесённой морали. |
| REQ-007 | PASS | Prompt содержит политику противоречащих версий и запрет выдавать выдуманный факт за канон. |
| REQ-008 | PASS | Prompt и тест объявляют ввод/контекст данными и запрещают раскрытие правил. |
| REQ-009 | PASS | `test_models_are_strict_and_frozen`, enum и union tests подтверждают strict/forbid/frozen/discriminated поведение. |
| REQ-010 | PASS | Catalog tests проверяют общие поля, ID и глобально уникальные нормализованные aliases. |
| REQ-011 | PASS | Character tests проверяют закрытый `AgeGroup`, traits и сериализацию `speech_style.register`. |
| REQ-012 | PASS | `test_catalog_accepts_all_three_profile_types` валидирует точные поля location/artifact и ссылки на character ID. |
| REQ-013 | PASS | Параметризованные locator tests принимают file:line и timecode и отклоняют остальные формы. |
| REQ-014 | PASS | Tests отклоняют duplicate ID, alias после `ё/е` и dangling resident/creator IDs; file adapter применяет тот же aggregate validator. |
| REQ-015 | PASS | Lookup tests подтверждают `strip → lower → ё/е` и сохранение пунктуации/внутренних пробелов. |
| REQ-016 | PASS | Tests отдельно проверяют точное совпадение ID, name и alias и отсутствие эвристического совпадения. |
| REQ-017 | PASS | `test_canon_filter_uses_or`, contract tests и runtime movie lookup подтверждают OR и пустой фильтр. |
| REQ-018 | PASS | Git JSON содержит объединённые `classic/shorts` и отдельные `pin`/`pin_movie` для противоречащей версии. |
| REQ-019 | PASS | Unit/CLI tests получают `found`, `not_found`, `ambiguous`; candidates сортируются `pin`, `pin_movie`. |
| REQ-020 | PASS | Lookup assertions проверяют один entity, отсутствие entity у not_found и полный список без автовыбора у ambiguous. |
| REQ-021 | PASS | Повторный lookup даёт одинаковый `model_dump_json`; CLI сортирует JSON keys. |
| REQ-022 | PASS | Один contract suite проходит для `InMemoryStructuredKnowledgeStore` и `GitStructuredKnowledgeStore`; сервис зависит от Protocol. |
| REQ-023 | PASS | `make run` и subprocess tests подтверждают `context`, `lookup`, `exit`. |
| REQ-024 | PASS | CLI tests проверяют UTF-8 JSON, startup validation до ready и ненулевой код на невалидных источниках. |
| REQ-025 | PASS | Реальные package data содержат character/location/artifact и дают все три lookup-статуса. |
| REQ-026 | PASS | Python 3.12.3, frozen uv sync и успешный `make test` без сети/инфраструктуры. |

## Проверка критериев приёмки

| Критерий | Статус | Доказательство |
| --- | --- | --- |
| Работающий CLI через `make run` | PASS | Runtime smoke test и 3 subprocess integration tests. |
| Полный System Context | PASS | Реальный Markdown, unit и integration проверки всех инвариантов. |
| Строгие неизбыточные Pydantic-модели | PASS | 15 model tests и ревью схем `models.py`. |
| Нормализация, aliases и canon OR | PASS | 12 table-driven lookup tests и 4 contract tests. |
| Три детерминированных lookup-статуса | PASS | Unit, integration и ручной runtime smoke. |
| Git JSON/Markdown и два adapter | PASS | Contract suite, file integration tests и wheel content check. |
| Невалидный справочник не обслуживается | PASS | Fault cases file adapter и CLI startup failure. |
| `make test` на Python 3.12 через uv | PASS | 40/40 тестов, 0 skipped, frozen sync успешен. |

## Известные ограничения

- CLI является локальным проверочным интерфейсом базового компонента, а не
  публичным сетевым API.
- Git-справочник намеренно минимален: он демонстрирует три типа сущностей и три
  результата lookup, но не претендует на полный каталог вселенной.
- Системный контекст и Structured Knowledge загружаются при создании файлового
  adapter; hot reload не предусмотрен.
- Возможности последующих изменений RAG не входят в проверенный scope.

## Вывод

Все REQ-001–REQ-026 и все критерии приёмки подтверждены. Этап `verify` для
`rag-base` успешно завершён.
