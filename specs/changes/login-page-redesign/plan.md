# План: редизайн страницы входа

Спецификация: [spec.md](./spec.md).

## Задача 1. Разметка и стили по макету

**Требования:** REQ-001–REQ-008.

**Критерии приёмки:** `/login/` соответствует согласованному макету; все
идентификаторы, используемые `login.js`, сохранены; абзаца под заголовком нет.

**Зависимости:** нет.

**Файлы:**

- `frontend/src/login/index.html`;
- `frontend/src/login/login.css`.

**Проверка:**

```sh
npm --prefix frontend test
npm --prefix frontend run test:proxy
npm --prefix frontend run build
```

Затем визуальное ревью и измерение viewport через Chrome DevTools Protocol.

## Задача 2. Документация

**Требования:** REQ-001–REQ-007.

**Критерии приёмки:** `frontend/README.md` описывает новый вид страницы;
`docs/README.md` ссылается на изменение.

**Зависимости:** задача 1.

**Файлы:**

- `frontend/README.md`;
- `docs/README.md`.

**Проверка:** ревью документации, затем `make test`.
