# Проверка: компактный `story-canon`

Исторический оригинал: `git show 5af56b5:specs/changes/story-canon/verification.md`.

## Результат

- make test 937 passed, 133 skipped (backend Pytest) 219 passed (frontend Node)
- make test-integration 1070 passed ```
- Ручная проверка на реальном пакете:
- `story-canon` отдаёт только персонажей; локации и артефакты для сюжета остаются в `lookup_knowledge`.
- Если у героя нет версии в запрошенном `continuity`, версия другого канона не подставляется.
- Правка отношения Кроша в `data/knowledge` — изменение данных, а не кода; после неё нужен `make knowledge-load` и обновление `encrypted/data.enc`.
- Реальные данные не коммитятся.
- Схема БД и миграции не менялись.
