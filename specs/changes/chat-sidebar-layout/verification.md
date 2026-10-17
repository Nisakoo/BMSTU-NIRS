# Verification: чат с боковой панелью «Мои истории»

Спецификация: [spec.md](./spec.md), план: [plan.md](./plan.md).
Дата проверки: 2026-10-17, ветка `main` (рабочая копия).

## Итоговые команды

| Команда | Результат |
| --- | --- |
| `make test` | frontend: 109 passed, 0 failed (4 новых теста `AgentApi`, 11 новых UI-тестов панели, 4 теста подсказки Кроша удалены вместе с подсказкой); backend: 279 passed, 17 skipped |
| `npm --prefix frontend run build` | успешная сборка |
| `docker compose ... up -d --build frontend` | страница отдаётся через Caddy на `127.0.0.1:8081` |
| Headless Chrome через DevTools Protocol с cookie вошедшего пользователя `sdd_krosh` | см. таблицу viewport и ручные сценарии |

## Viewport

Видимыми элементами за краем считаются только элементы с координатами внутри
окна: закрытая мобильная панель намеренно сдвинута за левый край
(`translateX(-100%)`) и не создаёт прокрутки.

| Viewport | `scrollWidth` | `scrollHeight` | Видимые элементы за краем | Наблюдение |
| --- | --- | --- | --- | --- |
| `1920x1080` | 1920 | 1080 | нет | панель слева, чат справа, колонка сообщений до `780px` |
| `1440x900` | 1440 | 900 | нет | соответствует выбранному макету |
| `1280x720` | 1280 | 720 | нет | страница не прокручивается |
| `768x1024` | 768 | 1024 | нет | панель скрыта, кнопка «Истории» в шапке |
| `375x800` | 375 | 800 | нет (и при открытой панели) | панель открывается поверх чата с затемнением |
| `320x640` | 320 | 640 | нет | тематические кнопки в три строки, поле ввода в окне |

## Ручные сценарии с реальным backend

- Открытие сохранённой истории из списка: показаны прежние сообщения,
  название в шапке, пункт выделен, статус «готов к идеям».
- Новая история через UI («Одной фразой: Нюша печёт пирог»): после ответа
  агента история появилась наверху списка с названием из запроса, выделена,
  название показано в шапке.
- Продолжение сохранённой истории с учётом контекста проверено в
  [user-dialog-history](../user-dialog-history/verification.md).

## Требования

| Требование | Проверка | Результат |
| --- | --- | --- |
| REQ-001 | Скриншоты и замеры: нет рамки, заголовка, персонажей, луны и подсказки; `scrollHeight` равен высоте окна | Выполнено |
| REQ-002 | Скриншоты `1440x900`; `ui.test.js`: `the sidebar shows the login and saved stories as text` | Выполнено |
| REQ-003 | Скриншоты: шапка с названием и статусом, колонка до `780px`, композер, чипы, холмы фоном | Выполнено |
| REQ-004 | Замеры `768`–`320`; скриншот открытой панели на `375x800`; `the history panel opens from the header and closes on choice or backdrop` | Выполнено |
| REQ-005 | `the sidebar shows the login and saved stories as text`, `a guest never requests the story list`; прежние тесты сессии | Выполнено |
| REQ-006 | `the sidebar shows…` (порядок, `Без названия`, без `aria-current`), `an empty story list explains where stories will appear`, `an answered new story appears…` (`aria-current="true"`) | Выполнено |
| REQ-007 | `opening a saved story shows its messages and streams that dialog`; ручной сценарий | Выполнено |
| REQ-008 | `a new story creates a fresh dialog with a greeting` | Выполнено |
| REQ-009 | `stories cannot be switched while the agent answers` | Выполнено |
| REQ-010 | `an answered new story appears in the list with its title and stays current`; `stories cannot be switched…` (повторная загрузка); ручной сценарий | Выполнено |
| REQ-011 | `a failed story list offers a retry while the chat keeps working`, `a missing story keeps the current dialog and reloads the list` | Выполнено |
| REQ-012 | `a 401 on the story list refreshes the session and retries once`; прежние тесты `401` для создания и отправки | Выполнено |
| REQ-013 | Ревью: динамический текст только через `textContent`, `innerHTML` не используется; тесты проверяют `textContent`; `dialog_id` не записывается в cookie, `localStorage` или URL | Выполнено |
| REQ-014 | Все прежние тесты чата проходят (блокировка до `ready`, буферизация, одна реплика, повтор через три секунды, Enter, чипы, выход) | Выполнено |
| REQ-015 | `agent-api.test.js`: `listDialogs reads…`, `getMessages reads an encoded dialog history`, `history requests map statuses to error codes`, `history requests reject malformed bodies` | Выполнено |

## Документация

Ревью: `frontend/README.md` (разделы о диалоговом потоке и боковой панели,
ссылки на SDD), `docs/README.md` (строка frontend-чата), `docs/dialogs.md`
(frontend-интеграция), `docs/auth.md` (расположение кнопки «Выйти»),
`AGENTS.md` (раздел «Реализованный frontend»).

## Известные ограничения

- Логика `script.js` была написана до новых UI-тестов этого изменения, а не
  строго после падающего теста; тесты добавлены в том же изменении и проверяют
  все сценарии спецификации.
- Placeholder поля ввода на узких экранах сокращается многоточием.
