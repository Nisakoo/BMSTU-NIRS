# Конфигурация Nginx для frontend: относительные редиректы и кэширование

## Цель

Frontend-контейнер использует стандартный `nginx:stable-alpine` с
`default.conf`. Для каталога без завершающего слеша Nginx отвечает абсолютным
редиректом со своим внутренним портом: при `make run`
`http://localhost:8080/login` ведёт на `http://localhost/login/` (порт 80), и
страница не открывается. То же для `/admin`. Диагностика подтвердила
первопричину: после `absolute_redirect off;` редирект сохраняет порт.
Кроме того, `Cache-Control` не задан, и браузер может эвристически кэшировать
HTML-страницы после пересборки.

Изменение добавляет собственный конфиг Nginx в `docker/`, чтобы сайт
открывался по любому адресу без слеша и всегда получал актуальные HTML.

## Требования

- REQ-001: `GET /login` и `GET /admin` через Caddy отвечают редиректом с
  относительным `Location` (`/login/`, `/admin/`), так что браузер остаётся на
  том же host и порту (`APP_PORT`). Переход по редиректу отдаёт `200` и
  страницу.
- REQ-002: `/`, `/login/`, `/admin/` и прямые пути к `index.html` отдают HTML с
  `Cache-Control: no-cache`.
- REQ-003: Хешированные Vite-ассеты в `/assets/` отдаются с
  `Cache-Control: public, max-age=31536000, immutable`; несуществующий ассет —
  `404`, а не HTML.
- REQ-004: Несуществующие пути вне `/api` отвечают `404`, как и раньше; SPA
  fallback не вводится. Маршрутизация `/api` в Caddy не меняется.
- REQ-005: Конфиг хранится в `docker/` и копируется в образ в
  `docker/frontend.Dockerfile`; healthcheck frontend продолжает работать.
- REQ-006: `docker/README.md`, `frontend/README.md` (раздел о production
  запуске) и при необходимости `docs/README.md` и `AGENTS.md` («Реализованный
  frontend») упоминают собственный конфиг Nginx, относительные редиректы и
  политику кэширования со ссылками на артефакты этой спецификации.

## Сценарии

### Адрес без слеша

- Given `make run` с `APP_PORT=8080`
- When пользователь открывает `http://localhost:8080/login`
- Then ответ `301` с `Location: /login/`, браузер открывает
  `http://localhost:8080/login/`

### Пересборка frontend

- Given пользователь уже открывал `/`
- When frontend пересобран и страница обновлена
- Then браузер ревалидирует HTML и получает ссылки на новые ассеты

### Несуществующий путь

- Given стек запущен
- When запрашивается `/nope` или `/assets/missing.js`
- Then ответ `404`

## Технологии и структура

- Новый файл `docker/nginx.conf` (server-блок на `listen 80`, `root
  /usr/share/nginx/html`, `absolute_redirect off`, `try_files`, `location` для
  `/assets/` и HTML). `docker/frontend.Dockerfile` копирует его в
  `/etc/nginx/conf.d/default.conf`.
- Учесть, что `add_header` во вложенном `location` отменяет унаследованные
  заголовки, а редирект на каталог формирует `try_files $uri/`.
- Caddy, backend, Vite dev server и `compose.yaml` не меняются.

## Команды

- Запуск: `make run`
- Тесты: `make test`

## Тестирование

Изменение затрагивает только конфигурацию контейнера, Python-код и JS
продукта не меняются, поэтому новые автоматические тесты не добавляются.
Проверка — ревью конфига и runtime в изолированном Compose-проекте через
`curl -sv`: `Location` у `/login` и `/admin`, `-L` до `200` на нестандартном
`APP_PORT`, заголовки `Cache-Control` у HTML и ассета, `404` у несуществующих
путей, healthy frontend. `make test` запускается как регрессия.

## Границы

- Всегда: все файлы контейнерного запуска — в `docker/`.
- Сначала спросить: SPA fallback, изменение Caddyfile, security-заголовки
  (CSP и т. п.).
- Никогда: публиковать порт Nginx на хосте; проксировать `/api` через Nginx.

## Критерии приёмки

- [ ] `/login` и `/admin` при нестандартном `APP_PORT` открываются без потери
  порта.
- [ ] HTML отдаётся с `no-cache`, ассеты `/assets/` — с `immutable`.
- [ ] Несуществующие пути — `404`; frontend healthy; чат, `/login/` и
  `/admin/` работают.
- [ ] Документация обновлена по REQ-006.
- [ ] `make test` проходит (регрессия; новых тестов нет, так как меняется
  только конфигурация).

## Открытые вопросы

- Нет.
