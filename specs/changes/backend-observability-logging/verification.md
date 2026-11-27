# Проверка: настраиваемое логирование backend

Исторический оригинал: `git show 5af56b5:specs/changes/backend-observability-logging/verification.md`.

## Результат

- Реализация соответствует [спецификации](./spec.md). Оба формата проверены автоматическими тестами и на локальном Compose-стеке. `request_id` возвращается в HTTP-ответе и сохраняется в фоновой операции; LLM и tool вызовы имеют отдельные идентификаторы и терминальные события с измеренной длительностью. Статистика токенов берётся только из подтверждённого streaming usage.
- Команды и результаты: `UV_CACHE_DIR=/private/tmp/smeshariki-uv-cache make test` — Успешно: 19 frontend и 143 backend теста
- Команды и результаты: `UV_CACHE_DIR=/private/tmp/smeshariki-uv-cache make lint` — Успешно: Ruff check и format check
- Команды и результаты: `LLM_MODEL=test/model docker compose -f docker/compose.yaml config --quiet` — Успешно
- Команды и результаты: `LLM_MODEL=test/model LOG_FORMAT=json LOG_LEVEL=DEBUG docker compose -f docker/compose.yaml up --build -d` — Успешно: backend и frontend собраны, стек healthy
- Команды и результаты: `curl -i -X POST http://127.0.0.1:8080/api/v1/dialogs` — `201 Created`, `Location` и `X-Request-Id`; JSON-логи связаны с ответом по `request_id`
- Команды и результаты: Пересоздание backend с `LOG_FORMAT=human LOG_LEVEL=INFO`, тот же HTTP-запрос и просмотр `docker compose logs backend` — Успешно: строка читаемая, содержит тот же набор применимых полей
- Команды и результаты: Повторная сборка backend с итоговым кодом и `LOG_FORMAT=json LOG_LEVEL=DEBUG`, тот же HTTP-запрос — Успешно: JSON строки содержат `timestamp`, ID, метод, маршрут, статус, `started_at`, `duration_ms`, `outcome`
- Команды и результаты: `docker compose -f docker/compose.yaml down` — Созданный для проверки стек остановлен
- Команды и результаты: `git diff --check` — Успешно
