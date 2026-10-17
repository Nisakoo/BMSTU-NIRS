# План: оценка ответов агента и качество в панели администратора

Спецификация: [spec.md](./spec.md). Реализуется после
[story-length-option](../story-length-option/spec.md).

## Порядок

Сначала доменный контракт и сервис на in-memory хранилище (фиксирует
поведение), затем HTTP и SSE. Рискованная часть — миграция и SQL оценок и
статистики — третьей, на временной PostgreSQL. Затем frontend чата, панель
администратора, документация и ручная проверка.

## Решения

- `HistoryStore.append` возвращает `tuple[int, ...]` — идентификаторы
  добавленных сообщений (в PostgreSQL — `messages.id`, в памяти — счётчик).
- `StoredMessage` получает `id` и `feedback`; `transcript` заполняет их.
- Новые операции хранилища: `set_feedback(owner_id, dialog_id, message_id,
  value)` и `clear_feedback(...)`; не найденное, чужое или пользовательское
  сообщение — `MessageNotFoundError`.
- `DialogEvent` для `message_end` получает `message_id`; SSE формирует
  `{"message_id": <id>}`.
- `AdminStatsStore` возвращает дополнительно `FeedbackStats`; запрос в
  `PostgresAdminStatsStore` считает ответы ассистента в окне и оценки этих
  ответов одним соединением.

## Задача 1. Домен и сервис

**Требования:** REQ-001 (контракт), REQ-002, REQ-003, REQ-005, REQ-013.

**Критерии приёмки:** установка, смена и снятие оценки в
`InMemoryHistoryStore`; отказ для сообщения пользователя, чужого диалога и
сообщения другого диалога; `transcript` отдаёт `id` и `feedback`;
`AgentService` публикует `message_end` с `message_id` сохранённого ответа.

**Файлы:** `backend/src/smeshariki_ai/dialogs/{history,models,errors,__init__}.py`,
`backend/src/smeshariki_ai/application/{agent_service,events}.py`,
`backend/tests/unit/dialogs/test_history.py`,
`backend/tests/unit/application/test_agent_service.py`.

**Проверка:** `uv run --project backend --locked pytest backend/tests/unit`.

## Задача 2. HTTP и SSE

**Требования:** REQ-002…REQ-005.

**Критерии приёмки:** `PUT`/`DELETE …/feedback` — `204`, `401` раньше
`404`/`422`, `404 {"detail":"Message not found."}`, `422`, `503`; история с
`id` и `feedback`; `message_end` с `message_id`.

**Файлы:** `backend/src/smeshariki_ai/api/{app,schemas}.py`,
`backend/tests/integration/api/test_dialog_history.py`,
`backend/tests/integration/api/test_message_feedback.py`,
`backend/tests/integration/api/test_sse.py`.

**Проверка:** `uv run --project backend --locked pytest backend/tests/integration/api`.

## Задача 3. Миграция, PostgreSQL и статистика

**Требования:** REQ-001, REQ-010.

**Критерии приёмки:** миграция `0003` с `CHECK` и каскадом;
`PostgresHistoryStore` проходит сценарии задачи 1; `append` возвращает
`messages.id`; `admin/stats` возвращает блок `feedback` с подсчётом по окну;
ошибки БД — недоступность.

**Файлы:** `backend/src/smeshariki_ai/db/{tables,history,admin_stats}.py`,
`backend/src/smeshariki_ai/db/migrations/versions/0003_message_feedback.py`,
`backend/src/smeshariki_ai/admin/{models,service,stores}.py`,
`backend/src/smeshariki_ai/api/admin.py`,
`backend/tests/integration/db/test_postgres_history.py`,
`backend/tests/integration/db/test_postgres_admin_stats.py`,
`backend/tests/unit/admin/`, `backend/tests/integration/api/test_admin_stats.py`.

**Проверка:** временный `postgres:17-alpine` и
`TEST_DATABASE_URL=… uv run --project backend --locked pytest backend/tests/integration/db`;
`make test`; `make lint`.

## Задача 4. Кнопки оценки в чате

**Требования:** REQ-006…REQ-009.

**Критерии приёмки:** Node-тесты `AgentApi` (`setFeedback`, `clearFeedback`,
`id`/`feedback` в истории); UI-тесты: кнопки только у завершённых ответов,
переключение и снятие, откат при ошибке, восстановление из истории, `401` —
один `refresh`.

**Файлы:** `frontend/src/{agent-api,script}.js`, `frontend/src/styles.css`,
`frontend/tests/{agent-api,ui}.test.js`.

**Проверка:** `npm --prefix frontend test`.

## Задача 5. Блок «Качество ответов» в админке

**Требования:** REQ-011, REQ-012.

**Критерии приёмки:** процент, лайки, дизлайки, «оценено N из M»; пустое
состояние; без метки «демо-данные»; обновление при смене периода.

**Файлы:** `frontend/src/admin/{admin-api,admin,demo-data}.js`,
`frontend/src/admin/index.html`, `frontend/src/admin/admin.css`,
`frontend/tests/admin-{api,ui,data}.test.js`.

**Проверка:** `npm --prefix frontend test`.

## Задача 6. Документация и ручная проверка

**Файлы:** `docs/dialogs.md`, `docs/database.md`, `docs/admin.md`,
`docs/README.md`, `frontend/README.md`, `AGENTS.md`.

**Проверка:** ревью; `make run` и `make migrate`; оценить ответ в чате и
увидеть его в панели администратора; скриншоты.
