# Verification: кнопка выхода в чате и панели администратора

Исторический оригинал: `git show 5af56b5:specs/changes/logout-button/verification.md`.

## Результат

- Итоговые команды: `make lint` — `All checks passed!`, 77 файлов отформатированы
- Итоговые команды: `make test` — frontend: 88 passed, 0 failed; backend: 232 passed, 7 skipped (интеграционные PostgreSQL/Redis без `TEST_*_URL`, как до изменения)
- Итоговые команды: `npm --prefix frontend run build` — успешная сборка
- Скриншоты сняты на Vite dev server без backend, поэтому страницы находились в состоянии «сервис недоступен»; на расположение кнопок это не влияет.
- Сквозной выход в браузере против запущенного backend не выполнялся. `POST /api/v1/auth/logout` покрыт существующими backend-тестами (`test_auth.py`), а поведение кнопок — Node-тестами с fake `fetch` и `location`.
