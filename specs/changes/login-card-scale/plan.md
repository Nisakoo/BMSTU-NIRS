# План: крупнее карточка входа и регистрации

Спецификация: [spec.md](./spec.md). План согласован вместе со спецификацией:
одна задача в одном файле.

## Задача 1. Размеры карточки

**Требования:** REQ-001…REQ-004.

**Изменения в `frontend/src/login/login.css`.** Значения из таблиц
спецификации у следующих селекторов:

- `.auth-layout` — колонка карточки, включая медиазапрос 1050px;
- `.auth-card`, `.auth-card::before`;
- `.auth-card-head h1`, `.auth-card-head p`;
- `.auth-tabs`, `.auth-tabs button`;
- `.auth-form`, `.auth-field`, `.auth-field label`, `.auth-field input`;
- `.auth-field-error`, `.auth-message`, `.auth-submit`;
- медиазапросы 860px и 570px.

**Проверка:**

- `npm --prefix frontend test` и сборка;
- пересборка frontend в Compose;
- через `cdp.mjs` на пяти размерах экрана:
  - минимальный `font-size` в карточке на входе и на регистрации с
    ошибками;
  - высоты элементов;
  - `scrollWidth`;
- скриншоты.
