# План: чистый stdout у `make knowledge-load`

## Основание

План реализует согласованную спецификацию
`specs/changes/knowledge-load-json-output/spec.md`. Изменение выполняется в
ветке `feat/knowledge-postgres-store` третьим коммитом до PR.

## Решения и зависимости

- В цели `knowledge-load` вызов `$(MAKE) --no-print-directory migrate`
  получает `>&2`. Отдельный вызов `docker compose run` для `load` образ не
  собирает, а его служебные сообщения Compose уже пишет в stderr.
- Проверка идёт в изолированном Compose-проекте `smeshariki-rag-verify`:
  `COMPOSE_PROJECT_NAME` перекрывает имя проекта, `ENV_FILE` указывает на
  временный env-файл в scratchpad. Локальный `docker/.env` и том
  `smeshariki-ai_postgres-data` не создаются.
- Синтетический пакет собирается из примеров `docs/knowledge.md` и
  дополняется отсутствующими в них `movies` и `krosh`, чтобы загрузка в пустую
  БД прошла.
- Сборка без кэша проверяется удалением образа проекта проверки перед
  запуском.

## Порядок реализации

1. Перенаправление вывода миграций и документация.
2. Verify и очистка ресурсов проверки.

## Задача 1. stdout цели и документация

**Связанные требования:** REQ-001–REQ-004.

**Критерии приёмки:** stdout с `FORMAT=json` — валидный JSON при сборке без
кэша и из кэша, при успешной и отменённой загрузке; при ошибке миграции
stdout пуст; текстовый отчёт и подсказки прежние; `docs/rag.md` описывает
контракт; diff `Makefile` затрагивает только цель `knowledge-load`.

**Зависимости:** нет.

**Файлы:** `Makefile`, `docs/rag.md`.

**Шаги:**

- RED: `make knowledge-load DIR=<пакет> FORMAT=json > out.json`, `json.load`
  падает на логе сборки.
- GREEN: добавить `>&2` к вызову `migrate`; повторить запуск — JSON валиден.
- REFACTOR: не требуется.

**Проверка:** ручные запуски цели по таблице «Тестирование» спецификации;
`git diff origin/main -- Makefile`; ревью `docs/rag.md`.

## Задача 2. Verify и очистка

**Связанные требования:** все.

**Критерии приёмки:** все критерии спецификации подтверждены;
`verification.md` записан; ресурсы проекта `smeshariki-rag-verify` и
временные контейнеры тестов удалены.

**Зависимости:** задача 1.

**Файлы:** `specs/changes/knowledge-load-json-output/verification.md`.

**Проверка:** `make lint`; `make test`; полный backend-набор с
`TEST_DATABASE_URL` (PostgreSQL 17) и `TEST_REDIS_URL`.
