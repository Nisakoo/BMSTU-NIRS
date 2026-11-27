# Проверка: benchmark BM25-поиска по лору

Исторический оригинал: `git show 5af56b5:specs/changes/lore-benchmark/verification.md`.

## Результат

- make test 923 passed, 133 skipped (backend Pytest) 219 passed (frontend Node)
- make test-integration 1056 passed ```
- Ручной прогон benchmark с готовыми ответами:
- Оценка ответов эвристическая: `required_facts` и маркеры отказа, а не семантический судья. Замена — отдельное изменение.
- Реальный LLM в тестах не вызывается; `LiteLLMAnswerer` проверен с детерминированным fake `LLMProvider`.
- Набор синтетический; реальные сценарии в репозиторий не коммитятся.
- `k=5` и порог отказа зафиксированы для benchmark; изменение — отдельное решение.
