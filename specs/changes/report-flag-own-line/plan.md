# План: флажок «Пожаловаться» всегда на своей строке

Спецификация: [spec.md](./spec.md).

## Задача 1. Отдельная строка для флажка

**Требования:** REQ-001–REQ-004.

**Решение:** `addFeedback` создаёт `<div class="sai-report-line">` с фразой
Смешарика, `addReport` добавляет в неё флажок; обёртка добавляется в строку
оценки. Стиль обёртки: `flex-basis:100%; display:flex; align-items:center;
justify-content:space-between`, у флажка `margin-left:auto`. Панель жалобы,
как и раньше, добавляется в строку оценки после обёртки. У `.sai-report`
убирается `margin-left:auto`.

**Файлы:** `frontend/src/script.js`, `frontend/src/styles.css`,
`frontend/README.md`.

**Проверка:** `make test`; пересборка frontend и ручная проверка через CDP
на 1280 и 390 px (положение флажка без оценки и с оценками 1–5, панель,
`scrollWidth`, скриншоты).
