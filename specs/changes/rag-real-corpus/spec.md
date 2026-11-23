# Реальный корпус RAG: 52 сценария и benchmark

## Цель

Довести структурированный канон до всего реального набора сценариев и
проверить BM25 на реальном корпусе, а не только на синтетическом наборе.

## Требования

- REQ-001: в `data/knowledge/episodes/` добавлены 52 эпизода второго
  плейлиста с номерами 33–84, `work: smeshariki` и уникальными slug.
- REQ-002: персонажи эпизода перечислены только при фактическом упоминании в
  тексте сценария; interactions, artifacts и locations не выдумываются.
- REQ-003: `python -m smeshariki_ai.rag check data/knowledge` подтверждает
  валидность: 84 эпизода, 9 персонажей, 10 локаций, 15 артефактов.
- REQ-004: реальный benchmark лежит в игнорируемом `data/lore-benchmark/`:
  `lore/` из 30 реальных документов, `questions.yaml` с 10 обычными вопросами
  (по три релевантных документа) и 5 ловушками, `answers.json`.
- REQ-005: `lore-benchmark` на реальном наборе запускается без БД и выдаёт
  `Recall@k`, `MRR`, `Accuracy` и `Correct Rejection Rate`.
- REQ-006: данные не коммитятся; в Git остаётся только зашифрованный архив,
  обновляемый владельцем данных.

## Сценарии

### Проверка канона

- Given 52 новых сценария в `data/scenarios/`
- When выполняется `rag check data/knowledge`
- Then пакет валиден и содержит 84 эпизода.

### Реальный benchmark

- Given 30 реальных документов и 15 вопросов
- When выполняется `lore-benchmark --answers ...`
- Then метрики посчитаны, ловушки отклонены, обычные ответы проходят
  `required_facts`.

## Технологии и структура

- `data/knowledge/episodes/*.yaml` — данные, вне Git.
- `data/lore-benchmark/` — реальный набор, вне Git.
- Код benchmark уже реализован в `rag/lore/benchmark.py`; изменений схемы и
  API нет.

## Команды

- `uv run --project backend --locked --no-sync python -m smeshariki_ai.rag check data/knowledge`
- `uv run --project backend --locked --no-sync python -m smeshariki_ai.rag lore-benchmark data/lore-benchmark/lore --questions data/lore-benchmark/questions.yaml --answers data/lore-benchmark/answers.json`

## Тестирование

| Требования | Проверка |
| --- | --- |
| REQ-001–REQ-003 | `rag check data/knowledge` |
| REQ-004–REQ-005 | `lore-benchmark` на реальном наборе; метрики записаны в `verification.md` |
| REQ-006 | Ревью: `data/` и `data/lore-benchmark/` отсутствуют в Git |

## Границы

- Всегда: не выдумывать факты и не добавлять сущности без источника.
- Сначала спросить: изменение формата знаний, коммит реальных данных.
- Никогда: не коммитить `data/` и не запрашивать кодовую фразу.

## Критерии приёмки

- [x] В каноне 84 эпизода.
- [x] `rag check` валиден.
- [x] Реальный benchmark собран и прогнан.
- [x] Метрики зафиксированы в `verification.md`.

## Открытые вопросы

- Нет.
