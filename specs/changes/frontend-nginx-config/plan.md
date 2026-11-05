# План: конфигурация Nginx для frontend

Спецификация: [spec.md](./spec.md).

## Порядок

Сначала конфиг и образ с runtime-проверкой (основной риск — наследование
`add_header` и редирект `try_files`), затем документация.

## Задача 1. `docker/nginx.conf` и Dockerfile

**Требования:** REQ-001…REQ-005.

**Критерии приёмки:** `docker/nginx.conf` содержит server-блок с
`absolute_redirect off`, `location /` с `try_files $uri $uri/ =404`,
`location /assets/` с `immutable` и `try_files $uri =404`, `no-cache` для
HTML (включая ответы на `/`, `/login/`, `/admin/`, отдаваемые через `index`);
`docker/frontend.Dockerfile` копирует его в
`/etc/nginx/conf.d/default.conf`; `nginx -t` в образе проходит.

**Файлы:** `docker/nginx.conf` (новый), `docker/frontend.Dockerfile`.

**Проверка:** runtime в изолированном проекте
`APP_PORT=18083 docker compose -p smeshariki-nginx -f docker/compose.yaml up -d --build --wait`:
`curl -sv http://127.0.0.1:18083/login` и `/admin` → `301`, `Location:
/login/`, `/admin/`; `curl -sL -o /dev/null -w '%{http_code} %{url_effective}'`
→ `200 http://127.0.0.1:18083/login/`; `curl -sI` у `/`, `/login/`,
`/admin/` → `Cache-Control: no-cache`; у ассета из `index.html` →
`immutable`; `/nope` и `/assets/missing.js` → `404`; frontend healthy;
`/api/v1/users/me` → `401`. Затем `down -v`.

## Задача 2. Документация и итоговая проверка

**Требования:** REQ-006.

**Проверка:** ревью `docker/README.md`, `frontend/README.md`,
`docs/README.md`, `AGENTS.md`; `make test` как регрессия.
