# План: кнопка времени не выделяется при открытой панели

Спецификация: [spec.md](./spec.md). План согласован вместе со спецификацией.

## Задача 1. Удалить открытое состояние

**Требования:** REQ-001…REQ-004.

**Изменения в `frontend/src/styles.css`.** Удалить правила:
- `.sai-length-button[aria-expanded="true"]`;
- `.sai-length-button[aria-expanded="true"]:hover:not(:disabled)`;
- `.sai-length-button[aria-expanded="true"] svg`.

**Проверка:**
- `npm --prefix frontend test` и сборка;
- пересборка frontend;
- CDP по шагам:
  - покой;
  - наведение;
  - клик;
  - курсор на ползунок;
  - курсор на кнопку при открытой панели;
  - повторный клик;
  - увод курсора;
- скриншоты.
