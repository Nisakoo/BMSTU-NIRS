# План: шрифт нижних кнопок боковой панели админки

Спецификация: [spec.md](./spec.md).

## Задача 1

**Требования:** REQ-001–REQ-003. В `admin.css`: `.adm-chat-link` и
`.adm-logout` — `font-size: 14px`; `.adm-logout` — `min-height: 44px`, в
правиле до 820 px — `38px`.

**Проверка:** `make test`; пересборка frontend и CDP на 1280 и 390 px.
