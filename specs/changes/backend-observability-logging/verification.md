# Проверка: настраиваемое логирование backend

## Итог

Реализация соответствует [спецификации](./spec.md). Оба формата проверены
автоматическими тестами и на локальном Compose-стеке. `request_id` возвращается
в HTTP-ответе и сохраняется в фоновой операции; LLM и tool вызовы имеют
отдельные идентификаторы и терминальные события с измеренной длительностью.
Статистика токенов берётся только из подтверждённого streaming usage.

## Требования и доказательства

| Требования | Результат проверки |
| --- | --- |
| REQ-001–REQ-003 | `test_backend_config.py`, `test_bootstrap.py`, `test_observability.py`: defaults, допустимые/недопустимые настройки, фильтрация, повторная настройка, UTC/JSON/human поля и отсутствие изменения root level; runtime Compose показал обе формы |
| REQ-004–REQ-005 | `test_dialogs.py`: `X-Request-ID` для 201, 202, 404, 503 и безопасного 500; JSON-события одного POST связаны с фоновой задачей, содержат метод, шаблон маршрута, статус, `started_at`, `duration_ms`; невалидный UUID не копируется в журнал. `test_agent_service.py` проверяет разные `request_id` для очередных сообщений одного диалога и параллельных диалогов |
| REQ-006 | `test_agent_service.py`, `test_runtime.py`, `test_tools.py`: `dialog_id`, контекст сообщения, номера итераций, `tool_call_id`, status и терминальная длительность; `test_litellm.py` проверяет `call_id` LLM |
| REQ-007–REQ-008 | `test_litellm.py`, `test_litellm_provider.py`: usage из чанка с пустым `choices`, точные входные/выходные/общие токены, отсутствие выдуманных чисел, безопасные ошибки и отмена, сохранение потока текста и tool calls |
| REQ-009 | `test_event_broker.py`, `test_sse.py`: переполненная подписка закрывается с предупреждением и `dialog_id`; остальные подписчики и фоновая задача продолжают работу |
| REQ-010–REQ-012 | `test_observability.py` и тесты agent/provider/service: уровни INFO/DEBUG/WARNING/ERROR, безопасные error types, отсутствие маркеров секрета и payload; ревью: Uvicorn access log отключён, LiteLLM verbose logger выключен в production bootstrap |
| REQ-013 | Ревью `docker/compose.yaml`, `docker/.env.example`, `docker/Dockerfile`, `docs/logging.md`, `docs/configuration.md`, `docs/README.md` и `AGENTS.md` |

## Команды и результаты

| Команда | Результат |
| --- | --- |
| `UV_CACHE_DIR=/private/tmp/smeshariki-uv-cache make test` | Успешно: 19 frontend и 143 backend теста |
| `UV_CACHE_DIR=/private/tmp/smeshariki-uv-cache make lint` | Успешно: Ruff check и format check |
| `LLM_MODEL=test/model docker compose -f docker/compose.yaml config --quiet` | Успешно |
| `LLM_MODEL=test/model LOG_FORMAT=json LOG_LEVEL=DEBUG docker compose -f docker/compose.yaml up --build -d` | Успешно: backend и frontend собраны, стек healthy |
| `curl -i -X POST http://127.0.0.1:8080/api/v1/dialogs` | `201 Created`, `Location` и `X-Request-Id`; JSON-логи связаны с ответом по `request_id` |
| Пересоздание backend с `LOG_FORMAT=human LOG_LEVEL=INFO`, тот же HTTP-запрос и просмотр `docker compose logs backend` | Успешно: строка читаемая, содержит тот же набор применимых полей |
| Повторная сборка backend с итоговым кодом и `LOG_FORMAT=json LOG_LEVEL=DEBUG`, тот же HTTP-запрос | Успешно: JSON строки содержат `timestamp`, ID, метод, маршрут, статус, `started_at`, `duration_ms`, `outcome` |
| `docker compose -f docker/compose.yaml down` | Созданный для проверки стек остановлен |
| `git diff --check` | Успешно |

## Ограничения проверки

- Реальный внешний LLM endpoint не вызывался: в Docker использована тестовая
  строка модели для проверки запуска и HTTP; usage проверен детерминированными
  потоковыми ответами SDK в тестах. Для upstream без usage ожидается
  `usage_available=false`.
- Стартовые сообщения самого Uvicorn остаются в его штатном формате; JSON и
  human настройка относится к событиям приложения `smeshariki_ai`. Стандартный
  Uvicorn access log отключён.
- Внутри filesystem sandbox команда `uv run` завершалась аварией macOS system
  configuration. Штатные команды `make test` и `make lint` были успешно
  запущены через `uv` вне sandbox с разрешением; результат продуктовых тестов
  не менялся.
