# Verification: оценки числами в «Качестве ответов» админки

Спецификация: [spec.md](./spec.md). Задача одна — `renderQuality`, разметка и
стили; план отдельно не выделялся.

| Проверка | Результат |
| --- | --- |
| `npm --prefix frontend test` | 214 passed |
| Headless Chrome 1440×1000, `/admin/` с подставными данными через `mountAdminPage` | Сводка «3,6 из 5» без картинки, строки 5…1 с числами в плашках |
| `docker compose up -d --build frontend` | Отданная `/admin/` без `adminFacesTemplate` |

| Требование | Чем подтверждено |
| --- | --- |
| REQ-001 | `answer quality shows the average score and numbered rows…`, `answer quality without ratings says so` |
| REQ-002, REQ-003 | Тот же тест: числа «5»…«1», доступные имена «Оценка N из 5: K» |
| REQ-004 | Ревью: шаблон и `FACES` удалены, `GET /api/v1/admin/stats` не менялся |
| REQ-005 | Скриншот 600×900 |
