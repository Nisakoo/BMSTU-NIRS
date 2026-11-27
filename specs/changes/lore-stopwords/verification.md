# Проверка: стоп-слова в BM25-поиске по лору

Исторический оригинал: `git show 5af56b5:specs/changes/lore-stopwords/verification.md`.

## Результат

- Добавлен модуль `rag/lore/stopwords.py`; оба анализатора удаляют стоп-слова; `LoreContextBuilder` использует общий список вместо собственной копии. На held-out golden set выросли все три метрики поиска, на подобранном наборе `Recall@5` снизился — это раскрыто ниже.
- `make test`: 1071 passed, 140 skipped (интеграционные ждут `TEST_DATABASE_URL`). `make lint` чист.
- По вопросам: `invention` 0.667 → 1.000, `mystery` 0.333 → 0.667, `games` 0.000 → 0.333, `weather` 0.333 → 0.000.
- Результаты: `Recall@5` — 0.450 — **0.483**
- Результаты: `MRR@5` — 0.637 — **0.713**
- Результаты: `Context Recall` — 0.283 — **0.300**
- Результаты: `Context Any-Relevant` — 0.750 — 0.750
- Результаты: `Trap Passage Rate` — 1.000 — 1.000
- Результаты: `Recall@5` — 1.000 — **0.933**
- Результаты: `MRR@5` — 0.950 — 0.950
- Результаты: `Context Recall` — 0.567 — **0.633**
- Результаты: `Context Any-Relevant` — 1.000 — 1.000
