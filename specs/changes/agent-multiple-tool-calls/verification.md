# Verification: несколько вызовов инструментов в одном ответе LLM

## Итог

Все требования и критерии приёмки `spec.md` подтверждены. `make lint` и
`make test` проходят. Запрос из раздела «Цель» на настоящих DeepSeek и
PostgreSQL получает ответ. Известное ограничение — в конце документа.

## Окружение

- macOS, Docker Compose проекта `smeshariki-ai`, модель
  `deepseek/deepseek-flash` через LiteLLM, пакет знаний из 68 сущностей в
  PostgreSQL 17.
- Ветка `feat/agent-multiple-tool-calls` от `main` (`41f007b`).

## Требования

| Требование | Проверка | Результат |
| --- | --- | --- |
| REQ-001 | `test_stream_assembles_several_interleaved_tool_calls_in_index_order`: три вызова с перемешанными фрагментами собраны по `index` | ✅ |
| REQ-002 | `test_stream_rejects_invalid_set_of_tool_calls` (повторный `id`, нет имени, нет `id`, отрицательный индекс), `test_stream_rejects_mixed_content_and_tool_calls`, `test_stream_wraps_malformed_responses` (не-JSON, не-объект) | ✅ |
| REQ-003 | `test_llm_response_classification_uses_explicit_status` (два вызова — `tool_call`), `test_invalid_llm_response_is_rejected` (текст с вызовом, пустой ответ) | ✅ |
| REQ-004 | `test_several_tool_calls_run_in_order_before_final_response`: одно сообщение ассистента и два результата по порядку | ✅ |
| REQ-005 | `test_tool_calls_beyond_the_limit_get_an_error_without_running`, `test_tool_call_limit_must_be_positive`, `test_tool_call_limit_defaults_to_four` | ✅ |
| REQ-006 | `test_stream_maps_several_tool_calls_into_one_assistant_message`, `test_stream_maps_tool_call_and_linked_result` | ✅ |
| REQ-007 | `test_runtime_logs_each_of_several_tool_calls_without_payload` (`tool_call_count`, события по каждому `tool_call_id`, отклонённый — `error`, payload нет); `tool_call_count` добавлен в белый список полей журнала | ✅ |
| REQ-008 | `test_cancellation_during_second_tool_call_propagates` | ✅ |
| REQ-009 | Ревью `docs/agent.md` (правила agent loop, провайдер, наблюдаемость, ссылки) и `AGENTS.md` (п. 2 и 7 runtime) | ✅ |
| REQ-010 | `test_stream_keeps_reasoning_of_tool_call_response_out_of_text`, `test_stream_drops_reasoning_of_final_response`, `test_stream_rejects_non_text_reasoning` | ✅ |
| REQ-011 | `test_reasoning_is_returned_with_tool_calls_and_not_to_the_user`, `test_stream_passes_reasoning_back_with_tool_calls`; отсутствие поля без рассуждений — точное сравнение в `test_stream_maps_tool_call_and_linked_result` | ✅ |

## Команды и результаты

```sh
uv run --project backend --locked pytest backend/tests/unit/agent   # 94 passed
make lint   # All checks passed, 151 files already formatted
make test   # frontend 219/219; backend 833 passed, 125 skipped
docker compose --env-file docker/.env -f docker/compose.yaml up -d --build backend
```

Пропуски backend — интеграционные тесты без `TEST_DATABASE_URL`; изменение их
не затрагивает.

## Проверка на настоящей модели

- До исправления: история «ассистент с вызовом без `reasoning_content` →
  результат» давала `400` и для одного, и для двух вызовов; с
  `reasoning_content` — принималась.
- После пересборки backend `Agent` с `LiteLLMProvider`, реальным
  `lookup_knowledge` на PostgreSQL и запросом «Придумай мне сказку про Кроша
  и Ежика с их любимыми предметами» (2 минуты чтения): `agent.llm.completed
  result_type="tool_call" tool_call_count=2`, два `rag.lookup.completed
  outcome="found"`, затем `result_type="final"` и `agent.run.completed
  iterations=2`; ответ — сказка на 1623 символа с фантиками и «Ёлки-иголки!».
- Первый шаг тем же запросом: 9 из 10 и 20 из 20 параллельных запусков
  провайдера успешны.

## Известное ограничение

Изредка (2 из 38 запусков) модель пишет текст перед вызовами в одном ответе.
Такой ответ по-прежнему считается некорректным (`A response cannot mix text
and tool calls`): спецификация сознательно сохранила это правило, а текст к
этому моменту уже передан пользователю потоком. Поддержка такого ответа —
отдельное изменение.

Ручная проверка в чате через браузер остаётся за пользователем.
