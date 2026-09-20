# Проверка: брокер событий диалога

## Итог

Изменение соответствует спецификации. Управление подписками вынесено из
`AgentService` в абстракцию `DialogEventBroker`; production composition root
использует `InMemoryDialogEventBroker`. Публичные HTTP- и SSE-контракты не
изменились.

## Проверка требований

| Требования | Доказательство | Результат |
| --- | --- | --- |
| REQ-001, REQ-002 | Ревью `application/event_broker.py` и `application/events.py`; тест абстрактности и потребительские тесты `DialogSubscription` | Пройдено |
| REQ-003–REQ-006 | Unit-тесты положительного queue size, независимых подписок, ordered broadcast, изоляции диалогов и отсутствия replay | Пройдено |
| REQ-007 | `test_overflow_closes_only_the_slow_subscriber` подтверждает неблокирующее удаление только переполненной подписки | Пройдено |
| REQ-008, REQ-009 | Unit-тесты идемпотентных unsubscribe/shutdown, очистки pending events, разблокировки `receive` и запрета новой подписки после shutdown | Пройдено |
| REQ-010 | `test_concurrent_operations_keep_subscribers_consistent` и ревью собственного `asyncio.Lock` брокера | Пройдено |
| REQ-011–REQ-013 | Recording broker в `test_agent_service.py` подтверждает обязательное constructor injection и делегирование subscribe, unsubscribe и всех `message_*` events; subscriber state в сервисе отсутствует | Пройдено |
| REQ-012 | `test_unknown_dialog_is_rejected_before_broker_subscription` подтверждает проверку `HistoryStore` до обращения к брокеру | Пройдено |
| REQ-014 | `test_shutdown_cancels_tasks_and_rejects_new_submissions` подтверждает отмену и ожидание agent task до `broker.shutdown()` | Пройдено |
| REQ-015 | Ревью `bootstrap.py` и `test_bootstrap_builds_service_with_explicit_provider`: composition root создаёт и передаёт `InMemoryDialogEventBroker` | Пройдено |
| REQ-016 | Интеграционные тесты dialogs, SSE, LiteLLM failure path и `/agent_test` подтверждают прежние коды HTTP, события, heartbeat и lifecycle | Пройдено |
| REQ-017 | Ревью импортов нового модуля: только стандартная библиотека и application event types; зависимостей от FastAPI, агента, истории, environment и внешнего брокера нет | Пройдено |
| REQ-018 | Ревью логирования и существующие log-safety тесты `AgentService`/LiteLLM: payload событий и тексты исключений не журналируются | Пройдено |
| REQ-019 | Обновлены `docs/dialogs.md`, глобальная схема `docs/README.md` и реализованный контракт в `AGENTS.md` | Пройдено |
| REQ-020 | Добавлены отдельные unit-тесты брокера и делегирования; весь продуктовый набор тестов выполняется без сети и внешней модели | Пройдено |

## Проверка критериев приёмки

- [x] `DialogEventBroker` является ABC, а `InMemoryDialogEventBroker` реализует
  контракт без внешних зависимостей.
- [x] `AgentService` не содержит коллекций подписчиков, очередей или алгоритма
  overflow и делегирует lifecycle внедрённому брокеру.
- [x] In-memory реализация обеспечивает ordered broadcast по `dialog_id`,
  bounded queues, отсутствие replay и изоляцию медленного подписчика.
- [x] Неизвестный диалог отклоняется до subscribe; disconnect и shutdown
  освобождают подписки и разблокируют потребителей.
- [x] Endpoint-ы, HTTP-коды, SSE frames, heartbeat и `/agent_test` сохранили
  наблюдаемое поведение.
- [x] Архитектурная документация соответствует реализации и composition root.
- [x] Полный набор тестов и Ruff проходят.

## Выполненные команды

```text
uv run --project backend --locked pytest backend/tests/unit/application/test_event_broker.py
10 passed

uv run --project backend --locked pytest backend/tests/unit/application/test_agent_service.py
15 passed

uv run --project backend --locked pytest backend/tests/unit/test_bootstrap.py backend/tests/integration/api/test_dialogs.py backend/tests/integration/api/test_agent_test.py backend/tests/integration/api/test_litellm_provider.py
17 passed

uv run --project backend --locked pytest backend/tests/integration/api/test_sse.py
5 passed

make test
125 passed

make lint
Ruff check: passed
Ruff format --check: 40 files already formatted

git diff --check
passed
```

## Известные ограничения

- Реализация хранит подписки только в одном процессе и теряет их при рестарте.
- Replay и `Last-Event-ID` не поддерживаются.
- Переполненная очередь закрывает только медленного подписчика; события для
  него не восстанавливаются.
- Размер очереди по умолчанию равен 64 и не настраивается через environment.
- Постоянный или межпроцессный брокер в изменение не входит.
