# Проверка: размещение статического frontend-прототипа в `src`

## Результат

Проверка завершена успешно 22 сентября 2026 года. Все файлы реализации
прототипа перенесены в `frontend/src/` без изменения содержимого. Статическая
страница и ресурсы работают с новым корнем сервера, документация обновлена,
регрессионные тесты проходят.

## Проверка требований

| Требования | Доказательство | Результат |
| --- | --- | --- |
| REQ-001 | Ревью итогового дерева и проверки отсутствия прежних путей | Выполнено: HTML, CSS, JavaScript и `static/characters/` находятся только под `frontend/src/` |
| REQ-002 | Сравнение SHA-256 до и после переноса | Выполнено: контрольные суммы всех пяти файлов совпадают |
| REQ-003 | Ревью `frontend/README.md`, `frontend/tests/.gitkeep` и отсутствия `frontend/src/.gitkeep` | Выполнено: README и tests сохранены на верхнем уровне, лишний маркер удалён |
| REQ-004 | HTTP smoke и снимок headless Chrome при корне `frontend/src/` | Выполнено: пять ресурсов получили HTTP 200 с корректными MIME-типами, страница визуально отрисована без изменений |
| REQ-005 | Ревью `frontend/README.md` и `docs/README.md` | Выполнено: структура, путь реализации и команда запуска используют `frontend/src/` |

## Критерии приёмки

- [x] Все пять файлов реализации находятся под `frontend/src/`, прежние пути
  в корне `frontend/` отсутствуют.
- [x] Контрольные суммы всех перенесённых файлов совпадают с состоянием до
  рефакторинга.
- [x] `frontend/src/.gitkeep` удалён, `frontend/README.md` и
  `frontend/tests/.gitkeep` сохранены.
- [x] HTTP-проверка и визуальный снимок подтверждают корректную загрузку при
  корне сервера `frontend/src/`.
- [x] Документация содержит итоговую структуру и актуальную команду запуска.
- [x] `make test` проходит успешно; структурные тесты не добавлены.

## Выполненные команды

```sh
shasum -a 256 frontend/smeshariki_ai.html frontend/styles.css frontend/script.js frontend/static/characters/krosh.png frontend/static/characters/kopatych.png
shasum -a 256 frontend/src/smeshariki_ai.html frontend/src/styles.css frontend/src/script.js frontend/src/static/characters/krosh.png frontend/src/static/characters/kopatych.png
find frontend -maxdepth 5 -print
uv run --no-project python -m http.server 4173 --bind 127.0.0.1 --directory frontend/src
curl --silent --show-error --output /dev/null --write-out '%{http_code} %{content_type} %{url_effective}\n' <resource-url>
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --headless=new --window-size=1440,1200 --screenshot=<temporary-path>/frontend-src.png http://127.0.0.1:4173/smeshariki_ai.html
UV_CACHE_DIR=/private/tmp/smeshariki-ai-uv-cache UV_PYTHON_INSTALL_DIR=/private/tmp/smeshariki-ai-uv-python make test
git diff --check
git status --short
```

Контрольные суммы после рефакторинга:

```text
51bbe7600328219c90362d4a9ea76cdee620a702e4f2265d487d16169b924e0a  frontend/src/smeshariki_ai.html
7acc3a76c51dde17edc510e8b5bda277d876cfaccca04d10c1469d4560d1a2f3  frontend/src/styles.css
736754eab5bb0b823825664a2aeb77a2c723d2d215353e3525fdfa2f797c2a85  frontend/src/script.js
2f3ae731bcb1d1de2c122d652f64322b8b0f263430799a93ad34fcd20a67dbae  frontend/src/static/characters/krosh.png
ee638c74239bf8b11d55693054439a3cc2caa13b9e3bee0964521f32a714ca75  frontend/src/static/characters/kopatych.png
```

Результаты итогового прогона:

- HTTP smoke: пять ответов `200`; типы `text/html`, `text/css`,
  `text/javascript` и `image/png`;
- визуальная проверка: заголовок, чат, фон, элементы управления и оба
  изображения персонажей отрисовались как до переноса;
- `make test`: `132 passed`;
- `git diff --check`: ошибок whitespace нет.

## Проверка scope

- Байтовое содержимое HTML, CSS, JavaScript и PNG не менялось.
- `frontend/README.md` и `frontend/tests/` не переносились в `src/`.
- Backend, Docker Compose, зависимости и frontend-стек не менялись.
- Новые автоматические тесты структуры не добавлялись; существующие тесты не
  отключались.

## Известные ограничения

- JavaScript по-прежнему использует демонстрационный ответ и не подключён к
  dialog API или SSE.
- Статический frontend не имеет сборщика и production-команды; для локального
  просмотра корнем сервера должен быть `frontend/src/`.
