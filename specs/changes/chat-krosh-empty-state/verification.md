# Verification: Крош в пустом чате

Исторический оригинал: `git show 5af56b5:specs/changes/chat-krosh-empty-state/verification.md`.

## Результат

- Порядок TDD соблюдён: новые UI-тесты сначала упали (13 падений, включая тесты, учитывавшие текстовое приветствие как сообщение), затем прошли после реализации.
- Итоговые команды: `make test` — frontend: 113 passed, 0 failed (4 новых UI-теста Кроша, 2 теста обновлены вместо проверки текстового приветствия); backend: 279 passed, 17 skipped
- Итоговые команды: `npm --prefix frontend run build` — успешно; `dist/assets/krosh-ClYw31XP.png`, в `dist/index.html` ссылка `/assets/krosh-ClYw31XP.png`
- Итоговые команды: `curl http://127.0.0.1:8081/assets/krosh-ClYw31XP.png` после пересборки frontend в Compose — `200 image/png`
- Итоговые команды: Headless Chrome через DevTools Protocol с cookie пользователя `sdd_krosh`, ожидание `img.decode()` — см. таблицу viewport
- Используется исходный `krosh.png` (около 900 КБ) без уменьшенной копии; он загружается один раз и кэшируется браузером.
