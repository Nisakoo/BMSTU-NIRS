# Verification: dialog-history-repair

Исторический оригинал: `git show 5af56b5:specs/changes/dialog-history-repair/verification.md`.

## Результат

- `make test` — frontend 219 passed, 0 failed; backend 751 passed, 103 skipped.
- 0 skipped.
- Node 22 локально не запускался.
- Вне scope найдено: при запуске с `deepseek/deepseek-flash` модель возвращает несколько параллельных tool calls, `LiteLLMProvider` отклоняет такой ответ (`TypeError: Only one tool call is supported.` → `LLMProviderError`), и агент не отвечает. `parallel_tool_calls=False` модель игнорирует. Ограничение одного tool call зафиксировано в `litellm-provider` в разделе «Сначала спросить», поэтому здесь не меняется.
- Пустые диалоги в базе и лимит списка в 50 диалогов сознательно оставлены поведением `user-dialog-history`.
