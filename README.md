# smeshariki-ai

НИРС-проект «Смешарики AI».

## Структура

- `frontend/` — пользовательский интерфейс;
- `backend/` — API, runtime агента, серверная бизнес-логика и RAG;
- `docker/` — единый контейнерный запуск Caddy, frontend и backend;
- `docs/` — краткий каталог архитектуры, реализации и контрактов;
- `specs/` — спецификации, планы и результаты проверки SDD-изменений.

Основной запуск собирает frontend и поднимает Caddy, Nginx и backend одним
Docker Compose проектом. Агент и RAG входят в состав backend-приложения.

## Команды

- `make run` — сборка и запуск всего приложения через Docker Compose;
- `make frontend` — отдельный Vite dev server при разработке frontend;
- `make test` — запуск frontend Node-тестов и backend Pytest;
- `make lint` — проверка Python-кода через Ruff;
- `make format` — автоматическое исправление и форматирование Python-кода.

После настройки `docker/.env` приложение доступно на
[`http://localhost:8080/`](http://localhost:8080/). Настройки и примеры HTTP-
запросов описаны в [`docker/README.md`](docker/README.md). Backend использует
настраиваемый LiteLLM-провайдер и in-memory историю; RAG и постоянное хранилище
пока не реализованы.

## Документация

Глобальная карта проекта и ссылки на тематические страницы компонентов находятся
в [`docs/README.md`](docs/README.md). Полные требования, планы и результаты
проверки остаются в `specs/`.
