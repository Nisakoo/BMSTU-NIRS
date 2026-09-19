# Архитектура и контракты smeshariki-ai

Этот каталог помогает быстро найти архитектурные границы, пояснения по
фактической реализации и действующие контракты. Он не заменяет SDD-
спецификации: требования, сценарии, планы и доказательства проверки находятся
в [`specs/changes/`](../specs/changes/).

Если краткое описание расходится с последней согласованной спецификацией и её
результатом проверки, источником истины являются спецификация и
`verification.md`.

## Карта проекта

| Часть | Назначение | Где смотреть |
| --- | --- | --- |
| `frontend/` | Каркас отдельно запускаемого пользовательского интерфейса; приложение пока не реализовано | [Frontend](../frontend/) |
| `backend/` | Единое приложение с HTTP API, application-слоем и runtime агента | [Backend](../backend/) |
| `docker/` | Контейнерный запуск backend и будущих инфраструктурных зависимостей | [Запуск и конфигурация](../docker/README.md) |
| `docs/` | Глобальная карта и тематические страницы архитектуры и контрактов | [Текущий каталог](./README.md) |
| `specs/` | Полные SDD-спецификации, планы, результаты проверки и реестр состояний | [SDD-артефакты](../specs/) |

## Тематические страницы

- [Агент](./agent.md) — `Agent`, `LLMProvider`, инструменты, `ToolRegistry` и
  ограничения agent loop.
- [Диалоги и HTTP API](./dialogs.md) — `AgentService`, хранение истории,
  очередь запросов, HTTP и наблюдаемость.
- [Конфигурация backend](./configuration.md) — корневой `Config`, загрузка
  environment и передача component-owned подконфигов.
- [Запуск backend](../docker/README.md) — Docker Compose, настройки и примеры
  тестовых запросов.

## Архитектура

Backend является модульным монолитом. HTTP-слой вызывает application-сервис,
который координирует историю и независимый от транспорта runtime агента.

```mermaid
flowchart LR
    Client[HTTP-клиент]

    subgraph Backend[backend / smeshariki_ai]
        Config[Config / config]
        API[FastAPI / api]
        Service[AgentService / application]
        History[HistoryStore / dialogs]
        Agent[Agent runtime / agent]
        LLM[LLMProvider / LiteLLMProvider]
        Tools[ToolRegistry]

        API --> Service
        Config --> Agent
        Config --> LLM
        Service --> History
        Service --> Agent
        Agent --> LLM
        Agent --> Tools
    end

    Model[Настроенный LLM endpoint]
    Environment[Process environment]

    Client --> API
    Environment --> Config
    LLM --> Model
```

Сборка конкретных зависимостей выполняется в
[`bootstrap.py`](../backend/src/smeshariki_ai/bootstrap.py). Внутренние слои не
создают LLM-провайдер, реестр инструментов или хранилище самостоятельно.

## Состояния компонентов

Краткий источник текущего состояния SDD-изменений —
[`specs/status.yaml`](../specs/status.yaml). Каталог использует такое
отображение статусов:

| Статус SDD | Состояние в каталоге | Значение |
| --- | --- | --- |
| `draft` | Специфицировано | Требования ещё не завершены или не согласованы |
| `in-queue` | Запланировано | Спецификация согласована и ожидает выполнения |
| `in-progress` | Реализуется | По изменению идёт активная работа |
| `done` | Проверено | Реализация прошла verify и имеет успешный `verification.md` |

| Компонент | Назначение | Состояние | Где реализация | Где конкретика |
| --- | --- | --- | --- | --- |
| Каркас проекта | Границы frontend, модульного backend и служебных каталогов | Проверено | [`frontend/`](../frontend/), [`backend/`](../backend/) | [spec](../specs/changes/project-scaffold/spec.md), [plan](../specs/changes/project-scaffold/plan.md), [verification](../specs/changes/project-scaffold/verification.md) |
| Agent runtime | Собственный ограниченный tool-calling loop и независимые контракты LLM и инструментов | Проверено | [`smeshariki_ai/agent`](../backend/src/smeshariki_ai/agent/) | [страница компонента](./agent.md), [spec](../specs/changes/agent-runtime/spec.md), [plan](../specs/changes/agent-runtime/plan.md), [verification](../specs/changes/agent-runtime/verification.md) |
| LiteLLM-провайдер | Асинхронный production-адаптер Chat Completions и отдельная provider-конфигурация | Проверено | [`agent/providers`](../backend/src/smeshariki_ai/agent/providers/) | [страница компонента](./agent.md), [spec](../specs/changes/litellm-provider/spec.md), [plan](../specs/changes/litellm-provider/plan.md), [verification](../specs/changes/litellm-provider/verification.md) |
| Конфигурация backend | Единая загрузка environment, корневой immutable `Config` и раздача подконфигов | Проверено | [`config.py`](../backend/src/smeshariki_ai/config.py), [`main.py`](../backend/src/smeshariki_ai/main.py), [`bootstrap.py`](../backend/src/smeshariki_ai/bootstrap.py) | [страница компонента](./configuration.md), [spec](../specs/changes/backend-config/spec.md), [plan](../specs/changes/backend-config/plan.md), [verification](../specs/changes/backend-config/verification.md) |
| Диалоги и HTTP API | Создание диалогов, фоновая очередь сообщений, история и HTTP-вход | Проверено | [`application`](../backend/src/smeshariki_ai/application/), [`dialogs`](../backend/src/smeshariki_ai/dialogs/), [`api`](../backend/src/smeshariki_ai/api/) | [страница компонента](./dialogs.md), [spec](../specs/changes/agent-dialog-api/spec.md), [plan](../specs/changes/agent-dialog-api/plan.md), [verification](../specs/changes/agent-dialog-api/verification.md) |

Прогресс отдельных задач здесь не ведётся: он остаётся в соответствующих SDD-
артефактах.

## Что пока не реализовано

Frontend-приложение, RAG и инструмент `search_knowledge`, streaming/SSE, CORS,
постоянное хранилище истории и авторизация относятся к будущим изменениям.
Существующие каталоги или согласованное архитектурное направление не означают,
что эти возможности уже доступны.
