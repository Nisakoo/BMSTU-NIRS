# Verification: навигация админки следит за прокруткой

Спецификация: [spec.md](./spec.md). Задача одна — `mountAdminNavigation`,
план отдельно не выделялся.

| Проверка | Результат |
| --- | --- |
| `npm --prefix frontend test` | 208 passed (7 новых тестов навигации) |
| `docker compose up -d --build frontend` | `/admin/` отвечает `200` |
| Headless Chrome 1280×800, разметка `/admin/` с открытым содержимым и настоящим `mountAdminNavigation`, прокрутка 0 / 650 / 1300 / до конца | Обзор → Активность → Пользователи → Жалобы |

В headless Chrome с виртуальным временем браузер не рисует кадры, поэтому не
отправляет `scroll` и не вызывает `requestAnimationFrame`. На тестовой странице
событие `scroll` отправлялось вручную, а `requestAnimationFrame` подменялся на
`setTimeout(…, 16)`; расчёт положения разделов шёл по настоящей вёрстке.

| Требование | Чем подтверждено |
| --- | --- |
| REQ-001 | `scrolling highlights the section that reached the reading line`; браузерная проверка |
| REQ-002 | `the bottom of the page highlights the last section`; браузерная проверка (до конца — «Жалобы») |
| REQ-003 | `a clicked section stays highlighted until its smooth scroll ends`, `without scrollend the click hold ends after a second`, `a browser hash change holds its section like a click` |
| REQ-004 | `hidden sections never move the highlight` |
| REQ-005 | `many scroll events in one frame are measured once and keep the hash` |
| REQ-006 | Прежние тесты навигации проходят без изменений |

## Ограничения

- В живом стеке с входом администратора проверка не выполнялась: пароля
  администратора нет.
