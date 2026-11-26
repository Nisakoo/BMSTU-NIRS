# План: стоп-слова в BM25-поиске по лору

## Задача 1. Модуль стоп-слов и фильтрация в анализаторах

- REQ-001, REQ-002, REQ-006; зависит от ничего.
- Файлы: `backend/src/smeshariki_ai/rag/lore/stopwords.py`,
  `backend/src/smeshariki_ai/rag/lore/analyzer.py`,
  `backend/tests/unit/rag/lore/test_stopwords.py`,
  `backend/tests/unit/rag/lore/test_analyzer.py`.
- Шаг: `STOP_WORDS` как frozenset нормальных форм и `drop_stop_words`;
  оба анализатора применяют фильтр после токенизации/лемматизации.
- Проверка:
  `uv run --project backend --locked --no-sync pytest backend/tests/unit/rag/lore/test_stopwords.py backend/tests/unit/rag/lore/test_analyzer.py`.

## Задача 2. Единый список для правила контекста

- REQ-003; зависит от задачи 1.
- Файлы: `backend/src/smeshariki_ai/rag/lore/context.py`,
  `backend/tests/unit/rag/lore/test_context.py`.
- Шаг: `NON_CONTENT_TERMS = STOP_WORDS` вместо собственного frozenset;
  поведение `select`/`build` не меняется, правило имён сохраняется.
- Проверка:
  `uv run --project backend --locked --no-sync pytest backend/tests/unit/rag/lore/test_context.py`.

## Задача 3. Поведенческие тесты поиска и инструмента

- REQ-006; зависит от задач 1–2.
- Файлы: `backend/tests/unit/rag/lore/test_services.py`,
  `backend/tests/unit/rag/lore/test_tool.py`,
  `backend/tests/unit/rag/lore/test_index.py`.
- Шаг: прогнать и при необходимости обновить ожидания, если служебные термы
  участвовали в запросах тестов; добавить проверку, что запрос из одних
  стоп-слов даёт `empty`.
- Проверка:
  `uv run --project backend --locked --no-sync pytest backend/tests/unit/rag/lore`.

## Задача 4. Контрольный прогон и документация

- REQ-004, REQ-005, REQ-007, REQ-008; зависит от задачи 3.
- Файлы: `docs/lore.md`, `docs/rag.md`, `AGENTS.md`.
- Шаг: прогон golden set с `--context`; фиксация чисел до/после; правка
  раздела «Предобработка» (там сказано, что стоп-слова не удаляются) и
  «Ограничения»; требование `make lore-load` после выкладки.
- Проверка: ревью; числа в документации совпадают с прогоном.

## Задача 5. Verify

- Критерии приёмки; зависит от всех.
- Файлы: `specs/changes/lore-stopwords/verification.md`, реестр через CLI.
- Шаг: `make test`, `make lint`, фиксация метрик и раскрытие всех замеренных
  вариантов списка; статус `done` после успешной проверки.
