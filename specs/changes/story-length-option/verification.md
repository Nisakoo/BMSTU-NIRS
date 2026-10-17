# Verification: выбор длины истории

Спецификация: [spec.md](./spec.md), план: [plan.md](./plan.md).
Дата проверки: 2026-10-17, ветка `feat/user-dialog-history`.

## Итоговые команды

| Команда | Результат |
| --- | --- |
| `make test` | frontend: 116 passed, 0 failed; backend: 299 passed, 17 skipped (интеграционные тесты PostgreSQL/Redis без `TEST_*_URL`) |
| `make lint` | `All checks passed!` |
| Пересборка `frontend` и `backend` в Compose, headless Chrome с cookie пользователя | см. ниже |

Порядок TDD соблюдён во всех задачах: тесты runtime, сервиса, API, клиента и
UI сначала падали, затем прошли.

## Ручная проверка с реальной моделью

Одинаковый запрос «Крош и Ёжик строят ракету» в двух новых диалогах через
API: `reading_minutes: 2` — 258 слов, `reading_minutes: 10` — 1462 слова (цели
300 и 1500). Оба ответа завершились `message_end`. В
`GET /api/v1/dialogs/{id}/messages` сообщение пользователя — ровно
«Крош и Ёжик строят ракету», без указания длины.

## Viewport композера

| Viewport | `scrollWidth` | `scrollHeight` | Видимые элементы за краем |
| --- | --- | --- | --- |
| `1440x900` | 1440 | 900 | нет |
| `375x800` | 375 | 800 | нет |
| `320x640` | 320 | 640 | нет |

## Требования

| Требование | Проверка | Результат |
| --- | --- | --- |
| REQ-001 | Ревью разметки (`<select id="saiLength" aria-label="Длина истории">`, нативный элемент управляется с клавиатуры); скриншоты | Выполнено |
| REQ-002 | `ui.test.js`: `the chosen story length is sent with every next request` (сохраняется после «+ Новая история»); ревью: значение не записывается в хранилища | Выполнено |
| REQ-003 | `agent-api.test.js`: `submitMessage adds the reading time only when it is chosen`; прежний `submitMessage sends the exact dialog request contract` | Выполнено |
| REQ-004 | `the length picker is locked together with the prompt` | Выполнено |
| REQ-005 | Таблица viewport | Выполнено |
| REQ-006 | `test_dialogs.py`: `test_reading_time_is_optional_and_reaches_the_agent`, `test_unsupported_reading_time_returns_422` (0, 3, 7, `"5"`, 5.5, `null`, `true`) | Выполнено |
| REQ-007 | `test_runtime.py`: `test_reading_time_adds_a_length_system_message` (2/5/10), `test_no_reading_time_adds_no_length_message`, `test_reading_time_accepts_only_supported_values`; ручная проверка | Выполнено |
| REQ-008 | `test_agent_service.py::test_reading_time_reaches_agent_but_not_history`; API-тест проверяет историю; ручная проверка | Выполнено |
| REQ-009 | Ревью: `reading_minutes` добавлен в разрешённые поля журнала и пишется в `agent.run.started` как число; текст запроса не журналируется | Выполнено |

## Документация

Ревью: `docs/agent.md`, `docs/dialogs.md`, `frontend/README.md`, `AGENTS.md`.

## Известные ограничения

- Длина — ориентир для модели: фактический объём отличается от целевого
  примерно на 10–15%.
