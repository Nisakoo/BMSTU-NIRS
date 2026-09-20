# Проверка: потоковые ответы агента через SSE и тестовый интерфейс

Дата проверки: 2026-09-19.

## Итог

Изменение соответствует согласованной спецификации. Production-путь использует
реальный асинхронный stream LiteLLM, agent loop передаёт только фрагменты
финального ответа, `AgentService` публикует изолированные in-memory события, а
FastAPI предоставляет SSE и самодостаточный `/agent_test`. Существующий пустой
`202 Accepted`, последовательность запросов диалога и правила сохранения истории
сохранены.

## Проверенные требования

| Требования | Свидетельство | Результат |
| --- | --- | --- |
| REQ-001, REQ-004, REQ-006 | `test_llm.py`: потоковый контракт и пустой детерминированный fake; `LLMTextDelta` принимает значимые whitespace fragments и запрещает пустой fragment | Выполнено |
| REQ-002–REQ-005 | `test_litellm.py`: `stream=True`, mapping сообщений и tools, последовательная выдача delta, пустой ответ, сборка фрагментированного tool call, mixed/malformed stream, безопасные ошибки, cancellation и конкурентность | Выполнено |
| REQ-007–REQ-010 | `test_runtime.py`: совместимость `run`, постепенный `Agent.stream`, скрытая tool iteration, пустой ответ, несовпадающий terminal text, mixed/multiple tool calls и лимит итераций | Выполнено |
| REQ-011–REQ-013 | `test_agent_service.py`: `message_start/delta/end`, сохранение до `message_end`, последовательная очередь, параллельные диалоги и безопасная ошибка после частичного текста без записи истории | Выполнено |
| REQ-014–REQ-015 | `test_agent_service.py`: broadcast нескольким подписчикам, закрытие переполненной очереди без блокировки агента, unsubscribe/shutdown и отсутствие зависимости обработки от наличия клиента | Выполнено |
| REQ-016–REQ-018 | `test_sse.py`: `text/event-stream`, `Cache-Control: no-cache`, точные JSON frames `ready/message_*` и heartbeat | Выполнено |
| REQ-019 | `test_sse.py`: 422 для некорректного UUID, 404 для неизвестного диалога и безопасный 503 после shutdown | Выполнено |
| REQ-020 | `test_agent_service.py::test_late_subscription_does_not_replay_completed_events` и документация `docs/dialogs.md` | Выполнено |
| REQ-021–REQ-022 | HTTP/service-тесты shutdown и disconnect cleanup; существующие `test_dialogs.py` подтверждают немедленный пустой 202 до завершения агента | Выполнено |
| REQ-023 | `test_agent_test.py`: `GET /agent_test`, `text/html`, один документ без CDN, внешних script/link и постоянного browser storage; wheel inspection подтверждает включение `agent_test.html` | Выполнено |
| REQ-024–REQ-027 | Ревью встроенного JavaScript: создание диалога, ожидание `ready`, EventSource, состояния UI, буферизация событий до 202, постепенный вывод, ошибки и новый диалог; JavaScript прошёл `node --check` | Выполнено |
| REQ-028–REQ-029 | Ревью `agent_test.html`: пользовательский и модельный текст вставляются только через `textContent`; используются relative same-origin API URL, внешние ресурсы и отдельный frontend отсутствуют | Выполнено |
| REQ-030 | Runtime/provider/service log-тесты с приватными маркерами; логи содержат только lifecycle metadata и типы ошибок | Выполнено |
| REQ-031 | Обновлены `docs/agent.md`, `docs/dialogs.md`, `docs/README.md`, `backend/README.md` и `AGENTS.md`; противоречащие утверждения об отсутствии streaming/SSE удалены | Выполнено |
| REQ-032 | Итоговые `make test` и `make lint` проходят без сетевого LLM | Выполнено |

## Критерии приёмки

- Реальный fragment выдаётся из `LiteLLMProvider.stream` до терминального
  `LLMResponse`; `Agent.stream` сохраняет порядок, а сохранённый полный текст
  совпадает с объединением fragments.
- Фрагментированный tool call собирается и исполняется внутри agent loop; SSE
  получает только fragments финального ответа.
- Пустой ответ, ошибка после частичного текста, медленный подписчик, отсутствие
  подписчиков, поздняя подписка и shutdown покрыты тестами; история меняется
  только при полном успехе.
- SSE endpoint выдаёт согласованные headers, `ready`, `message_*` и heartbeat;
  replay отсутствует.
- POST сообщения сохранил пустой немедленный `202 Accepted`.
- `/agent_test` упакован в wheel как единственный HTML resource, использует
  существующие API и безопасно выводит текст.
- Архитектурная документация соответствует реализации.
- Полный тестовый набор и Ruff проходят.

Все критерии приёмки подтверждены.

## Выполненные команды

```text
make format
All checks passed!
38 files left unchanged

make test
114 passed in 2.97s

make lint
All checks passed!
38 files already formatted

git diff --check
exit code 0

uv build --project backend --wheel --out-dir /tmp/smeshariki-ai-verify-dist
Successfully built smeshariki_ai-0.1.0-py3-none-any.whl

unzip -l ... | rg 'agent_test.html|api/app.py|application/events.py'
smeshariki_ai/api/agent_test.html найден в wheel
smeshariki_ai/api/app.py найден в wheel
smeshariki_ai/application/events.py найден в wheel

sed ... agent_test.html | node --check -
exit code 0
```

Проверочный каталог wheel после инспекции удалён из `/tmp`.

## Отключённые тесты и scope

- В тестовом наборе не обнаружены `skip` или `xfail`.
- Новых сетевых обращений, frontend-контейнера, CORS, replay/event store,
  аутентификации, API истории, RAG или новых зависимостей не добавлено.
- Автотесты проверяют поведение Python/HTTP/SSE. Для документации не создавались
  искусственные тесты существования файлов.

## Известные ограничения

- История, очередь запросов, подписки и SSE events остаются in-memory и теряются
  при рестарте процесса.
- Переподключение EventSource не воспроизводит пропущенные события;
  `Last-Event-ID` игнорируется.
- Медленный подписчик с переполненной очередью отключается, а agent loop
  продолжает работу.
- Отдельный GUI end-to-end runner в проект не добавлялся. HTTP-поведение страницы
  проверено интеграционным тестом, JavaScript — синтаксической проверкой Node и
  ревью обработчиков DOM/SSE.
