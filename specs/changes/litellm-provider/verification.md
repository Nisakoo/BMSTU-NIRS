# Verification: LiteLLM-провайдер и подмодуль LLM-провайдеров

Дата проверки: 19 сентября 2026 года.

## Результат

Изменение `litellm-provider` соответствует одобренной спецификации. Все 23
требования и критерии приёмки подтверждены поведенческими тестами либо ревью
реализации и конфигурации. Полный набор из 88 продуктовых Python-тестов и Ruff
проходит; тесты адаптера не обращаются к сети и не требуют настоящих
credentials.

## Проверка требований

| Требования | Подтверждение | Результат |
| --- | --- | --- |
| REQ-001–REQ-004 | Ревью `agent.providers`, удалённого `agent.llm` и импортов `Agent`; контракт, fake, LiteLLM-адаптер, config и ошибка находятся в подмодуле, а доменные модели остаются в `agent.models` | Пройдено |
| REQ-005 | 11 unit-тестов обязательных/default/optional полей, frozen и extra-forbid поведения, URL и числовых ограничений, маскирования API key в `repr`, `str` и `ValidationError` | Пройдено |
| REQ-006–REQ-007 | 12 unit-тестов `load_config` и bootstrap: все `LLM_*` переменные, blank-to-None, обязательный model, production `LiteLLMProvider` и только явная fake-подмена | Пройдено |
| REQ-008–REQ-011 | AsyncMock-тесты прямого `litellm.acompletion`, `stream=False`, всех настроек, текстовых ролей, function tools, assistant tool call и JSON `ToolResult`; входные модели не изменяются | Пройдено |
| REQ-012–REQ-014 | Табличные тесты `None`/пустого/обычного content, одного и нескольких tool calls, смешанного ответа, пустого choices, несовместимого объекта, сломанного JSON, JSON не в форме object и несериализуемого tool result | Пройдено |
| REQ-015–REQ-016 | Тесты безопасной `LLMProviderError`, exception cause, распространения `CancelledError` и `caplog` без prompt, tool metadata, key, base URL, ответа и текста исключения; ревью отсутствия callbacks/verbose | Пройдено |
| REQ-017 | Интеграционный HTTP-тест с настоящим `LiteLLMProvider` и управляемым async-double: пустой `202` возвращается до сбоя, история остаётся пустой, provider/service logs безопасны | Пройдено |
| REQ-018 | `uv lock --check`, LiteLLM `1.101.0`, дерево прямых зависимостей и поиск lock-файла; LangChain/LangGraph и Proxy отсутствуют | Пройдено |
| REQ-019 | `docker compose config` и ревью `.env.example`/Docker README: единственный сервис backend, все настройки перечислены, реальных секретов и frontend/Proxy нет | Пройдено |
| REQ-020 | Ревью `docs/agent.md`, глобальной Mermaid-карты `docs/README.md` и корневого `AGENTS.md` | Пройдено |
| REQ-021 | Import smoke фасада `smeshariki_ai.agent`; старые `LLMProvider`/`FakeLLMProvider` и новые LiteLLM-типы экспортируются, импортов удалённого `agent.llm` нет | Пройдено |
| REQ-022 | `make test`: 88 тестов с подменой каждого `acompletion`; реальный socket, LLM endpoint и API key не используются | Пройдено |
| REQ-023 | Unit-тест одного экземпляра provider с двумя `asyncio`-задачами: первый вызов заблокирован событием, второй стартует и завершается независимо, ответы не смешиваются | Пройдено |

## Выполненные команды

```text
make test
88 passed in 2.51s

make lint
All checks passed; 34 files already formatted

uv lock --project backend --check
Resolved 67 packages in 4ms

public import + installed version smoke
litellm 1.101.0; imports: ok

uv tree --project backend --depth 1
runtime: FastAPI 0.141.1, LiteLLM 1.101.0, Pydantic 2.13.5, Uvicorn 0.52.4
dev: HTTPX 0.28.1, Pytest 9.1.1, pytest-asyncio 1.4.0, Ruff 0.16.7

docker compose --env-file docker/.env.example -f docker/compose.yaml config
configuration valid

docker compose --env-file docker/.env.example -f docker/compose.yaml config --services
backend

git diff --check
успешно

search: old agent.llm imports / synchronous completion / asyncio.to_thread
совпадений в backend нет

search: langchain / langgraph packages in backend/uv.lock
совпадений нет
```

## Критерии приёмки

- Production composition root создаёт `LiteLLMProvider` из отдельного
  `LiteLLMProviderConfig` — подтверждено.
- `Agent` зависит только от доменного `LLMProvider`, публичные импорты сохранены
  — подтверждено.
- `agent.providers` содержит контракт и реализации, старый `agent.llm` удалён,
  доменные модели не перенесены — подтверждено.
- Обычный, пустой и tool-call ответы корректно преобразуются — подтверждено.
- Используется прямой `litellm.acompletion`; независимые вызовы выполняются
  конкурентно без общего request state — подтверждено.
- Tools только описываются для модели и исполняются `ToolRegistry`; mixed и
  multiple calls доходят до прежней проверки `Agent` — подтверждено.
- Внешние и mapping-сбои дают безопасную `LLMProviderError`, cancellation не
  перехватывается — подтверждено.
- Фоновый сбой сохраняет HTTP `202`, не изменяет историю и не раскрывает
  чувствительные данные в логах — подтверждено.
- Отсутствующий model и некорректные сетевые настройки останавливают startup без
  fake-fallback — подтверждено.
- LiteLLM зафиксирован через uv; LangChain, LangGraph, Proxy-контейнер и frontend
  в Compose отсутствуют — подтверждено.
- Environment template и архитектурная документация соответствуют реализации и
  не содержат секретов — подтверждено.
- `make test` и `make lint` успешно проходят без внешней модели — подтверждено.

## Известные ограничения

- Обязательная автоматическая проверка не выполняет оплачиваемый или сетевой
  запрос к реальному LLM; совместимость конкретных credentials, endpoint и
  модели проверяется оператором при локальном запуске.
- В одной конфигурации используется одна модель; Router, fallback-модели,
  балансировка, произвольные provider-specific параметры и callbacks не входят
  в изменение.
- Вызовы непотоковые: streaming и SSE не реализованы.
- Agent loop по-прежнему принимает не более одного tool call на ответ; модель
  должна поддерживать function calling, если реестр инструментов непуст.
