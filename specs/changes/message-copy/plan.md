# План: копирование сообщений в чате

Спецификация: [spec.md](./spec.md). Реализуется в ветке
`feat/user-dialog-history` до [message-report](../message-report/spec.md).

## Порядок

Сначала поведение копирования с запасным путём (рискованная часть —
отсутствие Clipboard API вне secure context), затем вывод кнопки под
сообщениями, затем стили и документация.

## Решения

- Функция `copyText(text)` в `script.js`: сначала
  `navigator.clipboard?.writeText`, при отсутствии или отказе — временный
  `textarea` (`readonly`, вне экрана) в `document.body`, `select()`,
  `document.execCommand("copy")`, удаление `textarea` в `finally`. Возвращает
  `true`/`false`; исключения наружу не выходят.
- Кнопка `sai-copy` создаётся функцией `addCopy(row, bubble)`: текст берётся
  из `bubble.textContent` в момент нажатия, поэтому кнопка не зависит от
  потоковой дописки.
- Сообщение пользователя получает кнопку сразу в `addMessage(..., "user")`.
  Ответ ассистента — в `showStory` для сохранённых ответов и по `message_end`
  для текущего (там же, где `addFeedback`); `message_error` её не добавляет.
  Для этого `addMessage` возвращает пузырь, а строка доступна как
  `bubble.parent`/`parentElement`; кнопка добавляется в строку после пузыря.
- Подпись «Скопировано» держится `window.setTimeout(…, 1500)`; повторное
  нажатие перезапускает таймер. Кнопка не блокируется `updateForm`.

## Задача 1. Копирование с запасным путём

**Требования:** REQ-002, REQ-003, REQ-004, REQ-005.

**Критерии приёмки:** точный текст уходит в `clipboard.writeText`; без
Clipboard API и при отказе срабатывает `execCommand`, `textarea` удаляется;
«Скопировано» возвращается через 1,5 с; двойной отказ даёт «Не удалось
скопировать»; сетевых запросов нет.

**Файлы:** `frontend/src/script.js`, `frontend/tests/ui.test.js`
(FakeElement: `select`, `body`, `execCommand`, `navigator.clipboard`).

**Проверка:** `cd frontend && npm test` (RED → GREEN).

## Задача 2. Кнопка под сообщениями

**Требования:** REQ-001, REQ-005, REQ-006.

**Критерии приёмки:** кнопка есть у сообщений пользователя, у ответов после
`message_end` и в открытой сохранённой истории; её нет у генерируемого ответа
и у `message_error`; нажатие работает при заблокированной форме.

**Файлы:** `frontend/src/script.js`, `frontend/src/styles.css`,
`frontend/tests/ui.test.js`.

**Проверка:** `cd frontend && npm test`.

## Задача 3. Документация

**Требования:** все (описание поведения).

**Файлы:** `frontend/README.md`, `AGENTS.md` (раздел «Реализованный
frontend»), `docs/README.md` при необходимости.

**Проверка:** ревью; `make test` целиком.

## Задача 4. Ручная проверка

`make run`: копирование на `http://localhost` и по IP машины по HTTP.
