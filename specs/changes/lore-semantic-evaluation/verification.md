# Verification: оценка семантического поиска

Гипотеза о повышении Recall@5 не подтвердилась. На тот момент pgvector решили
не внедрять. Позже гибридный поиск реализовали как opt-in в
[lore-hybrid-retrieval](../lore-hybrid-retrieval/verification.md).
Полный исходный отчёт: `git show 9b31004:specs/changes/lore-semantic-evaluation/verification.md`.

Один прогон на неизменённом golden: 84 документа, 188 чанков и 20 вопросов.
Применялись mean pooling, L2, косинус, взвешенное слияние и RRF. Три модели:
`rubert-tiny2`, `multilingual-e5-small`, `sbert_large_nlu_ru`.

| Вариант | doc Recall@5 | doc MRR@5 |
| --- | --- | --- |
| BM25 | 0.550 | 0.722 |
| dense rubert / e5 / sbert | 0.350 / 0.483 / 0.400 | 0.481 / 0.650 / 0.522 |
| hybrid 0.7 e5 | 0.567 | 0.717 |
| hybrid RRF e5 | 0.567 | 0.727 |
| query expansion | 0.583 | 0.738 |

Максимальный прирост Recall для гибрида составил один документ из 60.
Шум ASR, общие вопросы и длинные документы ограничили качество. Переписанные
запросы не проверялись. Код и корпус не менялись, эксперимент выполнялся во
временном `uv run --with transformers`; модели кешировались вне репозитория.
