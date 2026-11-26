# План: чистка корпуса лора

Порядок: правила и use case → CLI и Makefile → тесты → применение к трём
пакетам → перепрогон бенчмарков и документация → verify.

## Задача 1. Правила чистки и use case

- REQ-002, REQ-004, REQ-005, REQ-006; зависит от ничего.
- Файлы: `backend/src/smeshariki_ai/rag/lore/cleanup.py`,
  `backend/tests/unit/rag/lore/test_cleanup.py`.
- Шаг: правила как данные (`URL_LINE_RULE`, `WHITESPACE_RULE`) и
  `clean_package(path, apply: bool) -> CleanReport`; резервная копия в
  `data/.backups/<имя>-<UTC>/` рядом с каталогом данных, атомарная запись через
  временный файл, отчёт с числом документов, изменённых строк и удалённых
  символов.
- Тесты: удаление URL-строки и URL в начале текста; сохранение «Ха-ха-ха»,
  «9:00», `...`, дублей строк; метаданные неизменны; идемпотентность; dry-run
  не пишет; копия создаётся только при `--apply`; невалидный пакет не пишется.
- Проверка:
  `uv run --project backend --locked --no-sync pytest backend/tests/unit/rag/lore/test_cleanup.py`.

## Задача 2. Команда CLI и цель Makefile

- REQ-001, REQ-007; зависит от задачи 1.
- Файлы: `backend/src/smeshariki_ai/rag/cli.py`,
  `backend/tests/unit/rag/lore/test_lore_cli.py`, `Makefile`.
- Шаг: подкоманда `lore-clean <path> [--apply] [--format]`; dry-run по
  умолчанию; коды `0`/`1`/`2`; текстовый и JSON-вывод; цель
  `make lore-clean DIR=<path> [APPLY=1]` без Docker и БД.
- Проверка:
  `uv run --project backend --locked --no-sync pytest backend/tests/unit/rag/lore/test_lore_cli.py`;
  `make -n lore-clean DIR=data/lore APPLY=1` печатает команду с `--apply`.

## Задача 3. Применение к трём пакетам

- REQ-008; зависит от задачи 2.
- Файлы: `data/lore/documents/*.yaml`, `data/lore-golden/lore/documents/*.yaml`,
  `data/lore-benchmark/lore/documents/*.yaml`.
- Шаг: dry-run, затем `--apply` для каждого пакета; `lore-check` каждого
  пакета; повторный dry-run подтверждает идемпотентность.
- Проверка: `lore-check` валиден, повторный прогон без изменений.

## Задача 4. Перепрогон бенчмарков и документация

- REQ-009, REQ-010; зависит от задачи 3.
- Файлы: `docs/lore.md`, `AGENTS.md`.
- Шаг: прогон golden set и подобранного набора с `--context` и без; фиксация
  новых значений в документации; описание команды `lore-clean`, правила и
  списка того, что сознательно не чистится.
- Проверка: ревью; значения в документации совпадают с фактическим прогоном.

## Задача 5. Verify

- Критерии приёмки; зависит от всех.
- Файлы: `specs/changes/lore-corpus-cleanup/verification.md`, реестр через
  CLI-скрипт.
- Шаг: `make test`, `make lint`, фиксация метрик до/после и объяснение
  расхождений; статус `done` после успешной проверки.
