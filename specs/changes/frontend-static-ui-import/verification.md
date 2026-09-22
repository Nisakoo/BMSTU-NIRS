# Проверка: перенос статического frontend-прототипа

## Результат

Проверка завершена успешно 22 сентября 2026 года. Реализация соответствует
REQ-001–REQ-005 и всем критериям приёмки: пять проектных файлов перенесены без
изменения содержимого, существующий frontend-каркас сохранён, исходный каталог
очищен, документация обновлена, а статическая страница успешно загружается и
визуально отрисовывается.

## Проверка требований

| Требования | Доказательство | Результат |
| --- | --- | --- |
| REQ-001 | SHA-256 до и после переноса; ревью итогового дерева | Выполнено: HTML, CSS, JavaScript и два PNG находятся в `frontend/`, все пять контрольных сумм совпали |
| REQ-002 | Ревью `frontend/README.md`, `frontend/src/.gitkeep` и `frontend/tests/.gitkeep` | Выполнено: существующий каркас сохранён и не перезаписан |
| REQ-003 | HTTP smoke пяти ресурсов и headless Chrome screenshot при корне сервера `frontend/` | Выполнено: HTML, CSS, JavaScript и оба изображения получили HTTP 200 с корректными MIME-типами; стили и персонажи отображаются |
| REQ-004 | Проверка отсутствия `/Users/kseniablinkova/Desktop/NIRS` и поиск `.DS_Store` | Выполнено: исходное дерево удалено после переноса, `.DS_Store` в репозитории отсутствуют |
| REQ-005 | Ревью `frontend/README.md` и `docs/README.md` | Выполнено: описаны состав, запуск, отдельность от Docker и отсутствие интеграции с dialog/SSE API |

## Критерии приёмки

- [x] Пять проектных файлов находятся в `frontend/` по прежним относительным
  путям и имеют исходные контрольные суммы.
- [x] `frontend/README.md`, `frontend/src/` и `frontend/tests/` сохранены.
- [x] В репозитории и исходном дереве отсутствуют `.DS_Store`; исходный каталог
  удалён после успешного переноса.
- [x] Статический сервер отдаёт все ресурсы, а страница визуально отображается
  в headless Chrome при размере окна 1440×1200.
- [x] `frontend/README.md` и `docs/README.md` соответствуют реализации и
  ссылаются на SDD-артефакты.
- [x] `make test` проходит успешно; структурные тесты не добавлялись.

## Выполненные команды

```sh
shasum -a 256 /Users/kseniablinkova/Desktop/NIRS/smeshariki_ai.html /Users/kseniablinkova/Desktop/NIRS/styles.css /Users/kseniablinkova/Desktop/NIRS/script.js /Users/kseniablinkova/Desktop/NIRS/static/characters/krosh.png /Users/kseniablinkova/Desktop/NIRS/static/characters/kopatych.png
shasum -a 256 frontend/smeshariki_ai.html frontend/styles.css frontend/script.js frontend/static/characters/krosh.png frontend/static/characters/kopatych.png
find frontend -maxdepth 4 -print
find . -name .DS_Store -print
uv run --no-project python -m http.server 4173 --bind 127.0.0.1 --directory frontend
curl --silent --show-error --output /dev/null --write-out '%{http_code} %{content_type} %{url_effective}\n' <resource-url>
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --headless=new --window-size=1440,1200 --screenshot=<temporary-path>/frontend.png http://127.0.0.1:4173/smeshariki_ai.html
UV_CACHE_DIR=/private/tmp/smeshariki-ai-uv-cache UV_PYTHON_INSTALL_DIR=/private/tmp/smeshariki-ai-uv-python make test
git diff --check
git status --short
```

Итоговые контрольные суммы:

```text
51bbe7600328219c90362d4a9ea76cdee620a702e4f2265d487d16169b924e0a  frontend/smeshariki_ai.html
7acc3a76c51dde17edc510e8b5bda277d876cfaccca04d10c1469d4560d1a2f3  frontend/styles.css
736754eab5bb0b823825664a2aeb77a2c723d2d215353e3525fdfa2f797c2a85  frontend/script.js
2f3ae731bcb1d1de2c122d652f64322b8b0f263430799a93ad34fcd20a67dbae  frontend/static/characters/krosh.png
ee638c74239bf8b11d55693054439a3cc2caa13b9e3bee0964521f32a714ca75  frontend/static/characters/kopatych.png
```

Результаты итогового прогона:

- HTTP smoke: пять ответов `200`; типы `text/html`, `text/css`,
  `text/javascript` и `image/png`;
- визуальная проверка: заголовок, чат, элементы управления, фон и оба
  изображения персонажей отрисовались;
- `make test`: `132 passed`;
- `git diff --check`: ошибок whitespace нет.

Первый запуск тестов внутри sandbox не смог создать каталоги `uv` в домашней
директории, второй — обратиться к сети. Итоговый запуск с временными каталогами
`uv` и разрешённым скачиванием зафиксированного Python 3.12 завершился успешно;
это ограничение окружения проверки, а не реализации.

## Проверка scope

- Содержимое перенесённых HTML, CSS, JavaScript и PNG не менялось.
- Backend, Docker Compose, `Makefile`, зависимости и frontend-стек не менялись.
- Новые автоматические тесты структуры или документации не добавлялись.
- Существующие тесты не отключались и не помечались skip.

## Известные ограничения

- `script.js` использует демонстрационный заранее заданный ответ и пока не
  подключён к dialog API или SSE.
- Команда production-сборки и выбранный frontend-фреймворк отсутствуют; текущая
  версия предназначена для раздачи как статический сайт.
