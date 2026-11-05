# Verification: Крош в пустом чате

Спецификация: [spec.md](./spec.md), план: [plan.md](./plan.md).
Дата проверки: 2026-10-17, ветка `feat/user-dialog-history`.

## Итоговые команды

| Команда | Результат |
| --- | --- |
| `make test` | frontend: 113 passed, 0 failed (4 новых UI-теста Кроша, 2 теста обновлены вместо проверки текстового приветствия); backend: 279 passed, 17 skipped |
| `npm --prefix frontend run build` | успешно; `dist/assets/krosh-ClYw31XP.png`, в `dist/index.html` ссылка `/assets/krosh-ClYw31XP.png` |
| `curl http://127.0.0.1:8081/assets/krosh-ClYw31XP.png` после пересборки frontend в Compose | `200 image/png` |
| Headless Chrome через DevTools Protocol с cookie пользователя `sdd_krosh`, ожидание `img.decode()` | см. таблицу viewport |

Порядок TDD соблюдён: новые UI-тесты сначала упали (13 падений, включая
тесты, учитывавшие текстовое приветствие как сообщение), затем прошли после
реализации.

## Viewport

| Viewport | `scrollWidth` | `scrollHeight` | Видимые элементы за краем | Наблюдение |
| --- | --- | --- | --- | --- |
| `1920x1080` | 1920 | 1080 | нет | Крош с облачком по центру ленты |
| `1440x900` | 1440 | 900 | нет | совпадает с согласованным макетом |
| `1280x720` | 1280 | 720 | нет | Крош уменьшен по высоте окна, блок над полем ввода |
| `768x1024` | 768 | 1024 | нет | блок по центру |
| `375x800` | 375 | 800 | нет | блок помещается над полем ввода |
| `320x640` | 320 | 640 | нет | Крош уменьшен, облачко и подпись над полем ввода |

## Ручной сценарий с реальным backend

Новая история на `1440x900`: отправлен запрос «Одной фразой: Ёжик находит
гриб» — Крош исчез, в ленте сообщение пользователя и ответ агента, история
появилась наверху списка и выделена.

## Требования

| Требование | Проверка | Результат |
| --- | --- | --- |
| REQ-001 | `ui.test.js`: `the sidebar shows the login and saved stories as text`, `Krosh greets a new story…`; ревью шаблона в `index.html`; скриншоты | Выполнено |
| REQ-002 | `Krosh greets a new story and leaves once the first message is accepted`, `Krosh stays with the draft when the first message fails`; ручной сценарий | Выполнено |
| REQ-003 | `a saved story opens without Krosh, an empty one shows him` | Выполнено |
| REQ-004 | `a new story brings Krosh back after a conversation`, `a new story creates a fresh dialog with a greeting` | Выполнено |
| REQ-005 | Сборка и `curl` изображения; ревью: `alt="Крош"`, текст облачка — статическая разметка, `animation:none` при `prefers-reduced-motion: reduce` | Выполнено |
| REQ-006 | Таблица viewport | Выполнено |
| REQ-007 | Все прежние тесты чата и панели проходят | Выполнено |

## Документация

Ревью: `frontend/README.md` (раздел боковой панели, ссылки на SDD),
`docs/README.md` (строка frontend-чата), `AGENTS.md` (раздел
«Реализованный frontend»).

## Известные ограничения

- Используется исходный `krosh.png` (около 900 КБ) без уменьшенной копии; он
  загружается один раз и кэшируется браузером.
