# План: улучшение агента под DeepSeek Flash 1017

## Основание

План реализует `specs/changes/agent-improving/spec.md`. Пользователь одобрил
спецификацию и разрешил сразу перейти к плану и реализации без отдельного
ожидания.

## Решения и допущения

- «DeepSeek Flash 1017» — это `deepseek/deepseek-flash`, уже используемая в
  локальной конфигурации; отдельный суффикс версии в `LLM_MODEL` не вводится.
- `LLM_TEMPERATURE` — число `0…2`, по умолчанию `0.8`.
- `LLM_THINKING` — булево значение, по умолчанию `false`. Параметр `thinking`
  передаётся только моделям с префиксом `deepseek/`; `true` для остальных
  моделей отклоняется при загрузке конфигурации.
- `max_tokens`: `2 → 1200`, `5 → 3000`, `10 → 6000`; `null` — без ограничения.
  При включённом thinking провайдер добавляет резерв `3000` токенов.
- `get_context` удаляется полностью: модуль, тест, импорт, регистрация и
  актуальные упоминания в документации. Исторические SDD-артефакты не
  переписываются.
- `AGENT_SYSTEM_PROMPT` уже игнорируется `load_config`; задача закрепляет это
  тестом с нейтральным именем переменной, убирает активные упоминания и
  обновляет документацию.
- Промпт из раздела «Предлагаемый текст» спецификации переносится в
  `agent/prompts/system.md` без изменения смысла.

## Порядок реализации

1. Параметры генерации в конфигурации.
2. Передача параметров в LiteLLM и `max_tokens` в контракт провайдера.
3. Вычисление `max_tokens` в `Agent`.
4. Удаление `get_context`.
5. Новый системный промпт.
6. Environment, Compose и документация запуска.
7. Архитектурная документация и `AGENTS.md`.
8. Полная проверка и runtime-smoke на реальной модели.

## Задача 1. Параметры генерации в конфигурации

**Связанные требования:** REQ-004, REQ-005, REQ-009.

**Критерии приёмки:** `LiteLLMProviderConfig` содержит `temperature` и
`thinking` с безопасными defaults; `load_config` читает `LLM_TEMPERATURE` и
`LLM_THINKING`; невалидные значения и `LLM_THINKING=true` для не-DeepSeek
модели отклоняются; секреты не раскрываются.

**Зависимости:** нет.

**Файлы:** `backend/src/smeshariki_ai/agent/providers/config.py`,
`backend/src/smeshariki_ai/config.py`,
`backend/tests/unit/agent/providers/test_config.py`,
`backend/tests/unit/test_backend_config.py`.

**Шаги:** RED — тесты defaults, чтения env, диапазона температуры, thinking и
не-DeepSeek ошибки; GREEN — поля и загрузчик; REFACTOR — общий helper для
чтения provider-переменных при необходимости.

**Проверка:**

```sh
uv run --project backend --locked pytest \
  backend/tests/unit/agent/providers/test_config.py \
  backend/tests/unit/test_backend_config.py
```

## Задача 2. Параметры запроса LiteLLM и `max_tokens` в контракте

**Связанные требования:** REQ-004–REQ-008, REQ-011.

**Критерии приёмки:** `LLMProvider.stream` принимает необязательный
`max_tokens`; `FakeLLMProvider` совместим; `LiteLLMProvider` передаёт
`temperature`, `max_tokens`, а для DeepSeek — `thinking`; thinking-резерв
добавляется только при включённом thinking и заданном лимите; ошибки
провайдера остаются безопасными.

**Зависимости:** задача 1.

**Файлы:** `backend/src/smeshariki_ai/agent/providers/base.py`,
`backend/src/smeshariki_ai/agent/providers/litellm.py`,
`backend/tests/unit/agent/providers/test_litellm.py`.

**Шаги:** RED — тесты сигнатуры и содержимого `acompletion`; GREEN —
`max_tokens` в контракте, `_build_request`, `thinking` и резерв; REFACTOR —
вынести вычисление итогового лимита в небольшой helper.

**Проверка:**

```sh
uv run --project backend --locked pytest \
  backend/tests/unit/agent/providers/test_litellm.py
```

## Задача 3. Вычисление `max_tokens` в `Agent`

**Связанные требования:** REQ-006, REQ-008.

**Критерии приёмки:** для `reading_minutes` `2/5/10/null` провайдер получает
`1200/3000/6000/None`; лимит передаётся на каждой итерации agent loop;
существующее системное сообщение о длине сохраняется.

**Зависимости:** задача 2.

**Файлы:** `backend/src/smeshariki_ai/agent/runtime.py`,
`backend/tests/unit/agent/test_runtime.py`.

**Шаги:** RED — тест записи `max_tokens` в тестовом провайдере для четырёх
значений; GREEN — таблица и передача аргумента; REFACTOR — именованная
константа и helper.

**Проверка:**

```sh
uv run --project backend --locked pytest backend/tests/unit/agent/test_runtime.py
```

## Задача 4. Удаление `get_context`

**Связанные требования:** REQ-002, REQ-012.

**Критерии приёмки:** production bootstrap регистрирует только
`lookup_knowledge`; модуль и тест `get_context` удалены; тестовые fixture не
используют имя `get_context`; `lookup_knowledge` продолжает работать.

**Зависимости:** задача 3.

**Файлы:** `backend/src/smeshariki_ai/bootstrap.py`,
`backend/src/smeshariki_ai/agent/get_context.py` (удалить),
`backend/tests/unit/agent/test_get_context.py` (удалить),
`backend/tests/unit/test_bootstrap.py`,
`backend/tests/unit/agent/providers/test_litellm.py`.

**Шаги:** RED — bootstrap-тест ожидает только `lookup_knowledge`; GREEN —
удалить импорт, регистрацию, модуль и тест; обновить fixture-имена; REFACTOR —
проверить отсутствие ссылок в исходниках и тестах.

**Проверка:**

```sh
uv run --project backend --locked pytest \
  backend/tests/unit/test_bootstrap.py \
  backend/tests/unit/agent/providers/test_litellm.py \
  backend/tests/unit/rag/test_lookup_tool.py
```

## Задача 5. Новый системный промпт

**Связанные требования:** REQ-003.

**Критерии приёмки:** `agent/prompts/system.md` содержит правила plain-text,
русского языка, запрета Markdown/иероглифов/служебных пометок и упоминаний
инструментов; существующие правила сказки сохранены; loader возвращает
непустой trimmed-ресурс.

**Зависимости:** нет, но выполняется после задач 1–4, чтобы не смешивать
поведение.

**Файлы:** `backend/src/smeshariki_ai/agent/prompts/system.md`,
`backend/tests/unit/agent/test_prompts.py`.

**Шаги:** RED — обновить ожидания ключевых фраз; GREEN — заменить промпт;
REFACTOR — вычитать формулировки на противоречия.

**Проверка:**

```sh
uv run --project backend --locked pytest backend/tests/unit/agent/test_prompts.py
```

## Задача 6. Environment, Compose и документация запуска

**Связанные требования:** REQ-001, REQ-009, REQ-010.

**Критерии приёмки:** `docker/.env.example` содержит `LLM_TEMPERATURE` и
`LLM_THINKING`, не содержит `AGENT_SYSTEM_PROMPT`; Compose передаёт новые
переменные; `docs/configuration.md` и `docker/README.md` описывают defaults;
локальная устаревшая строка `AGENT_SYSTEM_PROMPT` удаляется из
неотслеживаемого `docker/.env`.

**Зависимости:** задача 1.

**Файлы:** `docker/.env.example`, `docker/compose.yaml`, `docs/configuration.md`,
`docker/README.md`, `docker/.env` (локально, не в Git).

**Шаги:** RED — ревью текущих файлов; GREEN — добавить/обновить значения;
REFACTOR — проверить, что секреты не попали в шаблон.

**Проверка:** ревью файлов и `docker compose --env-file docker/.env -f
docker/compose.yaml config --quiet` (если доступен Docker; иначе ревью).

## Задача 7. Архитектурная документация и `AGENTS.md`

**Связанные требования:** REQ-010, REQ-012.

**Критерии приёмки:** `docs/agent.md` описывает новые параметры, plain-text
промпт и отсутствие `get_context`; `docs/rag.md` и `docs/README.md` не
упоминают `get_context` как production-инструмент; `AGENTS.md` отражает
реализованное поведение.

**Зависимости:** задачи 2–6.

**Файлы:** `docs/agent.md`, `docs/rag.md`, `docs/README.md`, `AGENTS.md`.

**Шаги:** RED — поиск устаревших упоминаний; GREEN — обновить разделы и
ссылки; REFACTOR — вычитать на противоречия с `spec.md`.

**Проверка:** `grep -R "get_context\\|AGENT_SYSTEM_PROMPT"` по актуальной
документации и исходникам, ревью страниц.

## Задача 8. Полная проверка и runtime-smoke

**Связанные требования:** все REQ и критерии приёмки.

**Критерии приёмки:** `make test` и `make lint` проходят; реальный запрос к
DeepSeek Flash 1017 на 2/5/10 минут возвращает русский plain-text без
Markdown и иероглифов; thinking выключен по умолчанию; `get_context` не
вызывается; `lookup_knowledge` работает.

**Зависимости:** задачи 1–7.

**Файлы:** без production-изменений, только `verification.md` на этапе verify.

**Проверка:**

```sh
make test
make lint
```

Дополнительно — один или несколько реальных запросов через `Agent` с
`lookup_knowledge` и проверка `max_tokens`, `thinking`, формата и языка.

## Риски

- Слишком маленький `max_tokens` при включённом thinking может оставить
  финальный текст пустым; резерв `3000` проверяется реальным запросом.
- `thinking` — параметр DeepSeek; для других моделей его нельзя передавать
  без риска ошибки. Поэтому `true` для не-DeepSeek отклоняется.
- Модель может нарушить plain-text правило несмотря на промпт; это фиксируется
  как известное ограничение, а не скрывается постобработкой.
- Удаление `get_context` затрагивает только демонстрационный инструмент;
  `lookup_knowledge` и RAG не меняются.

## Проверка плана

- [ ] Каждая задача имеет связанные требования и критерии приёмки.
- [ ] Для Python-задач указана точная команда pytest.
- [ ] Документация проверяется ревью, без структурных автотестов.
- [ ] Рискованные предположения вынесены в начало.
- [ ] `make test` и `make lint` запланированы на итоговое состояние.
