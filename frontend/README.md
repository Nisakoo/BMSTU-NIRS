# Frontend

Frontend `smeshariki-ai` — vanilla JavaScript приложение. В основном запуске
его собирает Vite, раздаёт Nginx, а Caddy направляет `/api` и SSE в backend.
Vite proxy остаётся отдельным режимом локальной разработки.

## Состав

- `src/index.html` — главная страница чата;
- `src/styles.css` — стили страницы;
- `src/script.js` — DOM и состояния пользовательского интерфейса;
- `src/agent-api.js` — HTTP/SSE-клиент без зависимости от DOM;
- `src/admin/` — отдельная страница административного макета, её стили,
  поведение и локальные демонстрационные данные;
- `src/auth-api.js` — клиент контракта аутентификации без зависимости от DOM;
- `src/auth-session.js` — общая проверка сессии с одним `refresh` и пути
  переходов по роли;
- `src/login/` — страница входа и регистрации `/login/`, её стили и поведение;
- `src/static/characters/` — изображения персонажей;
- `tests/` — детерминированные Node-тесты сетевого контракта и состояний UI;
- `vite.config.js` — root, build output и proxy `/api`;
- `package.json` и `package-lock.json` — npm-команды и зафиксированные
  зависимости.

## Основной запуск

Из корня репозитория настройте `docker/.env` по шаблону
`docker/.env.example`, затем выполните:

```sh
make run
```

Откройте `http://localhost:8080/` (или порт из `APP_PORT`) для пользовательского
чата, `http://localhost:8080/admin/` для административного макета либо
`http://localhost:8080/login/` для страницы входа и регистрации.
Frontend, Caddy и backend работают в одном Compose проекте; отдельные `npm ci`
и `make frontend` для этого сценария не требуются. Все браузерные запросы
остаются на одном origin. Caddy передаёт `/api/*` в backend, а статические
страницы — Nginx.

## Vite dev-режим

Установите frontend-зависимости один раз:

```sh
npm --prefix frontend ci
```

Для Vite proxy нужен доступный на хосте API. После `make run` он доступен через
Caddy на `127.0.0.1:8080`, поэтому запустите Vite так:

```sh
BACKEND_URL=http://127.0.0.1:8080 make frontend
```

Откройте [`http://127.0.0.1:5173/`](http://127.0.0.1:5173/).
Административный макет доступен по
[`http://127.0.0.1:5173/admin/`](http://127.0.0.1:5173/admin/).

Vite принимает браузерные запросы `/api/*` на своём origin и проксирует их в
backend. Default target при запуске без `BACKEND_URL` —
`http://127.0.0.1:8000`, если backend запущен отдельно. Для другого адреса
задайте переменную процесса Vite:

```sh
BACKEND_URL=http://127.0.0.1:9000 make frontend
```

FastAPI не включает CORS middleware: и в основном запуске, и в Vite dev-режиме
браузер обращается к API через тот же origin, с которого загружена страница.

## Команды

```sh
npm --prefix frontend run dev
npm --prefix frontend test
npm --prefix frontend run test:proxy
npm --prefix frontend run build
```

`test:proxy` проверяет локальный Vite proxy для HTTP и SSE с временным fake
backend без браузера.

Сетевой клиент сохраняет корректный контекст вызова browser `fetch`; Node-тесты
проверяют этот случай отдельно, поскольку обычный fake `fetch` его не выявляет.

Production bundle создаётся в игнорируемом каталоге `frontend/dist/`.

## Диалоговый поток

При загрузке после проверки сессии frontend создаёт новый диалог, открывает
`EventSource` и параллельно загружает список историй `GET /api/v1/dialogs`.
Поле ввода доступно только после события `ready`. Сообщение отправляется через
`POST /api/v1/dialogs/{dialog_id}/messages`, а ответ собирается из
`message_start`, `message_delta`, `message_end` и `message_error`.
Если создание диалога временно не удалось, форма остаётся заблокированной,
а frontend повторяет попытку каждые три секунды. После восстановления backend
страницу перезагружать не нужно.

Frontend допускает один незавершённый запрос, буферизует быстрые SSE-события до
получения `202 Accepted` и вставляет пользовательский и модельный текст,
названия историй и ошибки только через `textContent`.

## Боковая панель «Мои истории»

Чат занимает весь экран без внешней рамки: слева панель шириной `280px` с
логотипом, кнопкой «+ Новая история», списком «Мои истории», логином
пользователя и кнопкой «Выйти»; справа шапка с названием текущей истории и
индикатором состояния, лента сообщений в колонке до `780px`, поле ввода и
тематические кнопки. Приглушённые ночные холмы остаются фоном у нижнего края.
Страница целиком не прокручивается — прокручиваются список историй и лента.

- Нажатие на историю сначала загружает `GET /api/v1/dialogs/{dialog_id}/messages`
  и только после успеха закрывает прежний `EventSource`, показывает сообщения и
  открывает поток выбранного диалога; при ошибке пользователь остаётся в
  текущем диалоге, а `404` дополнительно обновляет список.
- Пустая история встречает пользователя Крошем по центру ленты: изображение,
  облачко «Ёлки-иголки, привет!…» и подпись «Напиши идею или выбери тему
  ниже». Блок задан `<template id="saiKroshTemplate">` в `index.html`, поэтому
  Vite включает изображение в сборку. Крош исчезает, когда первое сообщение
  принято (`202`); при ошибке отправки остаётся. Сохранённая история с
  сообщениями открывается без него.
- «+ Новая история» создаёт новый диалог и снова показывает Кроша.
- Под каждым завершённым ответом ассистента — «Как тебе история?» и пять
  мордашек Смешариков (балл 1–5: Ёжик грустит, Нюша недовольна, Лосяш
  задумался, Копатыч доволен, Крош в восторге) с `aria-label` и
  `aria-pressed`. При наведении и фокусе мордашка увеличивается и
  показывает подпись. Нажатие ставит балл, повторное снимает, другая
  мордашка меняет; рядом появляется фраза Смешарика. При ошибке состояние
  откатывается с сообщением «Не удалось сохранить оценку». У ответа с ошибкой
  мордашек нет; сохранённые истории показывают свои оценки. Картинки
  (PNG 256×256: голова персонажа на прозрачном фоне, чтобы эмоция читалась без подписи) лежат в `src/static/faces/` и подключены `<template id="saiFacesTemplate">` (в
  админке — `adminFacesTemplate`), поэтому Vite включает их в сборку.
- Список «Длина» со значком часов слева от кнопки отправки («Любая»,
  «2 мин», «5 мин», «10 мин»; та же высота 48 px и скругление, что у
  кнопки) передаёт `reading_minutes` с каждым запросом; выбор действует до
  перезагрузки страницы и блокируется вместе с полем ввода.
- Пока отправляется запрос или агент отвечает, переключение историй и новая
  история недоступны.
- После `message_end` список перезагружается: новая история появляется наверху
  со своим названием и остаётся выделенной (`aria-current="true"`).
- Ошибка списка показывает «Не удалось загрузить истории» и кнопку «Повторить»,
  чат при этом работает.
- `dialog_id` не сохраняется в cookie, `localStorage` или URL: перезагрузка
  начинает новую историю, прежние доступны в списке.

До `820px` панель скрыта и открывается кнопкой «Истории» в шапке поверх чата с
затемнением; выбор истории, новая история или нажатие на затемнение её
закрывают. Тематические кнопки переносятся на несколько строк. Начиная с
`320px` горизонтальной прокрутки нет.

## Панель администратора

`/admin/` является второй HTML-entry того же Vite-проекта и попадает в тот же
production build и Nginx-контейнер, что и пользовательский чат. Отдельный
frontend-сервис или порт не создаётся. Пользовательская страница по `/` и её
HTTP/SSE-поведение от admin-entry не зависят.

Макет использует связанную с пользовательским режимом тёмную сине-фиолетовую
палитру, скруглённые панели и светящиеся акценты, но не загружает и не
показывает персонажей. На странице представлены сводные карточки, активность
диалогов, показатели качества агента и список последних пользователей.
Переключение периода между 7, 30 и 90 днями обновляет все секции без
перезагрузки.

Перед показом страница проверяет сессию через `src/auth-session.js`: гостя
переводит на `/login/`, пользователя с ролью `user` — в чат, при недоступности
backend показывает сообщение. Затем `src/admin/admin-api.js` загружает
`GET /api/v1/admin/stats` для выбранного периода: карточки «Всего
пользователей» и «Активные пользователи», число новых пользователей и список
последних пользователей берутся из базы. Диалоги, сообщения, активность и
качество ответов пока берутся из `src/admin/demo-data.js` и помечены
«демо-данные». Контракт и источники данных — в
[`docs/admin.md`](../docs/admin.md).
Администратор создаётся командой `make create-admin LOGIN=<login>`. Кнопка
«Выйти» в нижней части боковой панели (на узких экранах — в правом верхнем
углу) завершает сессию и открывает `/login/`.

На desktop используется боковая навигация и многоколоночная аналитическая
сетка. На tablet и mobile навигация становится компактной, секции переходят в
одну колонку, а записи пользователей отображаются карточками без
горизонтальной прокрутки страницы.
## Страница входа и регистрации

`/login/` — вторая HTML-entry того же Vite build и Nginx-контейнера. Страница
выполнена в стилистике чата: ночная сцена (звёзды, луна, холмы) является фоном
всего окна без внешней рамки и отступов. Слева логотип, слоган «Сочиняй
истории вместе со Смешариками» и групповое изображение
`src/static/characters/smeshariki.png` на холмах у нижнего края; справа —
единственная подложка страницы, стеклянная карточка формы с сегментированным
переключателем «Вход»/«Регистрация». На desktop от `1280x720` страница не
прокручивается; на узких экранах блоки выстраиваются в одну колонку над формой
на фоне той же сцены.

Поля проверяются до отправки по правилам контракта. Регистрация отправляет
`POST /api/v1/users`, затем выполняет вход; после успешного входа страница
переходит в `/admin/` для администратора и в чат `/` для пользователя. Если при
открытии уже есть действительная сессия (в том числе восстановленная через
`refresh`), страница сразу выполняет тот же переход. Пароль хранится только в поле формы, сессия —
только в `HttpOnly` cookie, которую браузер выставляет сам.

Контракт описан в [`docs/auth.md`](../docs/auth.md) и реализован backend:
access JWT и refresh-токен передаются `HttpOnly` cookie.

## Доступ к чату

Чат по `/` до создания диалога проверяет сессию: гость переходит на
`/login/`, истёкший access-токен продлевается через `refresh`, а сбой backend
оставляет страницу с заблокированной формой и повторяет проверку через три
секунды. `401` у создания диалога или отправки вызывает один `refresh` и
повтор; ошибка SSE запускает проверку сессии и при необходимости переоткрывает
поток. Кнопка «Выйти» в боковой панели чата вызывает `POST /api/v1/auth/logout` и
после успеха открывает `/login/`; при ошибке страница остаётся на месте с
сообщением в строке статуса, которая на узких экранах показывается для
состояния ошибки. Подробная таблица переходов и поведение выхода — в
[`docs/auth.md`](../docs/auth.md#проверка-сессии-во-frontend).

## Ограничения

- Диалог и история хранятся только в памяти backend и теряются при рестарте.
- Перезагрузка страницы создаёт новый диалог; browser persistence отсутствует.
- SSE не поддерживает replay, поэтому потерянные при разрыве события не
  восстанавливаются.
- Основной Compose запуск использует локальный HTTP без публичного домена и
  автоматического HTTPS. Vite proxy остаётся только dev-контрактом.

Требования интеграции находятся в
[`spec.md`](../specs/changes/frontend-agent-integration/spec.md), порядок работ —
в [`plan.md`](../specs/changes/frontend-agent-integration/plan.md), результаты
проверки — в
[`verification.md`](../specs/changes/frontend-agent-integration/verification.md).

Повторное создание диалога после временной ошибки описано в
[`spec.md`](../specs/changes/frontend-dialog-retry/spec.md) и
[`verification.md`](../specs/changes/frontend-dialog-retry/verification.md).
Исправление browser `fetch` описано в
[`spec.md`](../specs/changes/frontend-fetch-binding/spec.md) и
[`verification.md`](../specs/changes/frontend-fetch-binding/verification.md).
Прежняя раскладка чата со сценой и подсказкой Кроша (заменена боковой
панелью из `chat-sidebar-layout`) описана в следующих изменениях.
Адаптивная геометрия и жизненный цикл подсказки Кроша описаны в
[`spec.md`](../specs/changes/frontend-responsive-layout/spec.md), порядок работ —
в [`plan.md`](../specs/changes/frontend-responsive-layout/plan.md), результаты
проверки — в
[`verification.md`](../specs/changes/frontend-responsive-layout/verification.md).
Ноутбучная базовая геометрия, wide-screen масштаб и мобильный режим только с
чатом уточнены в
[`spec.md`](../specs/changes/frontend-laptop-baseline-mobile-chat/spec.md),
[`plan.md`](../specs/changes/frontend-laptop-baseline-mobile-chat/plan.md) и
[`verification.md`](../specs/changes/frontend-laptop-baseline-mobile-chat/verification.md).
Правило скрытия подсказки после прямого нажатия на textarea или выбора типа
истории описано в
[`spec.md`](../specs/changes/frontend-krosh-hint-input-dismiss/spec.md),
[`plan.md`](../specs/changes/frontend-krosh-hint-input-dismiss/plan.md) и
[`verification.md`](../specs/changes/frontend-krosh-hint-input-dismiss/verification.md).
Административный макет описан в
[`spec.md`](../specs/changes/admin-dashboard-frontend/spec.md), порядок
реализации — в
[`plan.md`](../specs/changes/admin-dashboard-frontend/plan.md), результаты
проверки — в
[`verification.md`](../specs/changes/admin-dashboard-frontend/verification.md).
Редизайн страницы входа описан в
[`spec.md`](../specs/changes/login-page-redesign/spec.md) и
[`verification.md`](../specs/changes/login-page-redesign/verification.md);
сцена без внешней рамки — в
[`spec.md`](../specs/changes/login-fullbleed-scene/spec.md) и
[`verification.md`](../specs/changes/login-fullbleed-scene/verification.md).
Чат с боковой панелью описан в
[`spec.md`](../specs/changes/chat-sidebar-layout/spec.md) и
[`verification.md`](../specs/changes/chat-sidebar-layout/verification.md);
Крош в пустом чате — в
[`spec.md`](../specs/changes/chat-krosh-empty-state/spec.md) и
[`verification.md`](../specs/changes/chat-krosh-empty-state/verification.md);
выбор длины истории — в
[`spec.md`](../specs/changes/story-length-option/spec.md) и
[`verification.md`](../specs/changes/story-length-option/verification.md);
оценка ответов — в
[`spec.md`](../specs/changes/answer-feedback/spec.md) и
[`verification.md`](../specs/changes/answer-feedback/verification.md), мордашки —
в [`spec.md`](../specs/changes/answer-rating-faces/spec.md) и
[`verification.md`](../specs/changes/answer-rating-faces/verification.md).
Проверка сессии и переходы по роли описаны в
[`spec.md`](../specs/changes/auth-route-guard/spec.md) и
[`plan.md`](../specs/changes/auth-route-guard/plan.md), проверка — в
[`verification.md`](../specs/changes/auth-route-guard/verification.md).
Страница входа описана в
[`spec.md`](../specs/changes/auth-frontend-contract/spec.md) и
[`plan.md`](../specs/changes/auth-frontend-contract/plan.md), проверка — в
[`verification.md`](../specs/changes/auth-frontend-contract/verification.md).
Единый контейнерный запуск описан в
[`spec.md`](../specs/changes/compose-caddy-nginx-stack/spec.md), его проверка — в
[`verification.md`](../specs/changes/compose-caddy-nginx-stack/verification.md).
