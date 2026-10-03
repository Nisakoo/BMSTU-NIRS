# Проверка: подсказка Кроша до выбора способа начать историю

## Итог

Изменение успешно прошло verify 2026-09-27. На desktop подсказка видна рядом с
Крошем после загрузки и автоматического фокуса. Она скрывается после прямого
pointer/touch-нажатия на textarea или выбора тематической кнопки. На mobile
подсказка остаётся скрытой вместе с декоративной сценой.

## Проверка требований

| Требование | Доказательство | Результат |
| --- | --- | --- |
| REQ-001 | Chrome runtime на `1366px`: подсказка отображается рядом с Крошем и изначально не содержит `is-hidden` | Пройдено |
| REQ-002 | Node-тест `automatic focus keeps the Krosh hint visible` | Пройдено |
| REQ-003 | Node-тест проверяет идемпотентное скрытие после `pointerdown` и `touchstart`; Chrome runtime подтвердил переход в `is-hidden` после pointerdown | Пройдено |
| REQ-004 | Node-тест `choosing a preset dismisses the Krosh hint` одновременно проверяет скрытие, заполнение строки и autosize | Пройдено |
| REQ-005 | Повторные pointer/touch-события безопасны; существующие тесты Enter/Shift+Enter, autosize и отправки проходят | Пройдено |
| REQ-006 | Node-тест проверяет, что focus, keydown, input, paste и drop не скрывают подсказку; успешная отправка также оставляет её видимой без предшествующего pointer/chip | Пройдено |
| REQ-007 | Chrome computed-style на `375px` и `820px`: подсказка имеет `display: none` вместе с mobile-декором | Пройдено |
| REQ-008 | Изменены только vanilla JavaScript, тесты, документация и SDD-артефакты; API, SSE, responsive CSS и backend не менялись | Пройдено |
| REQ-009 | `frontend/README.md` и `docs/README.md` описывают фактическое правило и содержат ссылки на артефакты изменения | Пройдено |

## Выполненные команды

### Полный набор продукта

```sh
make test
```

Результат:

- frontend Node: `23 passed`, `0 failed`;
- backend Pytest: `146 passed` за `3.42s`;
- код завершения `0`.

### Production build

```sh
npm --prefix frontend run build
```

Результат: Vite `8.3.0`, `6 modules transformed`, production bundle успешно
создан, код завершения `0`.

### Проверка diff

```sh
git diff --check
```

Результат: ошибок whitespace нет, код завершения `0`.

### Runtime-проверка Chrome

При локальном Vite server Chrome DevTools Protocol проверил desktop `1366px`:
подсказка видима до `pointerdown` и получает `is-hidden` после него. На mobile
`375px` и `820px` сохранён `display: none`.

## Проверка критериев приёмки

- [x] Подсказка видна рядом с Крошем после desktop-загрузки и автоматического
  фокуса.
- [x] Pointer/touch-нажатие на textarea скрывает её идемпотентно.
- [x] Выбор тематической кнопки заполняет textarea и скрывает подсказку.
- [x] Непоинтерные события textarea и отправка сами по себе её не скрывают.
- [x] До `820px` mobile остаётся без декоративной сцены и подсказки.
- [x] `make test` и production build проходят успешно.
- [x] Документация соответствует реализации.

## Известные ограничения

- Runtime-проверка выполнялась с Vite без backend; сетевой контракт отдельно
  покрыт успешными Node- и backend-тестами.
