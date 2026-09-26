# Проверка: пример инструмента `get_context`

## Результат

Критерии [спецификации](./spec.md) подтверждены. Production bootstrap регистрирует `get_context`; вызов с `{}` возвращает фиксированную строку, вызов с лишним аргументом получает `invalid_arguments`. Agent loop передаёт результат обратно модели и принимает финальный ответ.

## Требования и доказательства

| Требование | Проверка | Результат |
| --- | --- | --- |
| REQ-001 | `test_bootstrap_builds_service_with_explicit_provider`; ревью bootstrap и API | Имя и схема инструмента передаются агенту; отдельного маршрута нет |
| REQ-002, REQ-003 | `test_get_context_returns_fixed_text_on_every_call`; ревью `get_context.py` | Точная строка возвращается повторно; внешние источники не используются |
| REQ-004 | `test_get_context_rejects_unexpected_arguments` | Лишние аргументы отклоняются как `invalid_arguments` |
| REQ-005 | `test_agent_passes_get_context_result_to_model` | Результат присутствует в следующем контексте LLM, финальный ответ успешен |
| REQ-006 | Ревью `docs/agent.md` и `docs/README.md` | Контракт и место инструмента в архитектуре описаны |

## Команды

- `make test` с `LITELLM_LOCAL_MODEL_COST_MAP=True`: 19 frontend и 146 backend тестов прошли.
- `make lint`: Ruff check и format check прошли, 47 файлов соответствуют форматированию.
- `git diff --check`: замечаний нет.

Команды с `uv` запускались вне sandbox: внутри него текущий `uv` завершается до старта Python при чтении macOS system configuration.

## Ограничения

Тест с детерминированным LLM подтверждает обработку вызова, но конкретная внешняя модель сама выбирает, вызывать ли инструмент. Внешний LLM endpoint в этой проверке не запускался.
