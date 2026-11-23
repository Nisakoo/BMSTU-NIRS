# Проверка выбора голоса и Ceph

## Итог

Изменение реализовано. Выбор голоса хранится во frontend, каждый запрос
озвучки перегенерирует MP3, файлы лежат в Ceph, метаданные — в PostgreSQL.

## Проверенные требования

| Требование | Проверка | Итог |
| --- | --- | --- |
| REQ-001–REQ-006 | Node-тесты меню голоса, `localStorage`, отсутствие надписи «Голос» | ✅ |
| REQ-007–REQ-013 | Node-тесты действия, polling, плеера, скачивания и смены голоса | ✅ |
| REQ-014–REQ-019 | API-тесты `voice`, `audio_voices`, перегенерации и сохранения старого объекта | ✅ |
| REQ-020–REQ-027 | PostgreSQL-интеграция, Ceph-сценарий, backfill legacy-записей | ✅ |
| REQ-028–REQ-032 | `docker compose config`, запуск `ceph-rgw`, здоровье сервисов | ✅ |
| REQ-033 | Ревью `docs/audio.md`, `docs/database.md`, `docs/configuration.md`, `docs/dialogs.md`, `docker/README.md`, `frontend/README.md`, `AGENTS.md` | ✅ |

## Команды

| Команда | Результат |
| --- | --- |
| `make lint` | успешно, форматирование проверено |
| `make test` | 931 passed, 129 skipped (PostgreSQL/Redis без env) |
| `make test-integration` | 1060 passed |
| `docker compose --env-file docker/.env -f docker/compose.yaml up -d --build --wait` | все сервисы healthy, включая `ceph-rgw` |
| `GET /` на `127.0.0.1:8090` | `200` |

## Ручной сценарий Ceph

Создан тестовый пользователь, диалог и ответ ассистента. Через API выполнены
две озвучки: `aidar` и `xenia`.

- `POST .../audio {"voice":"aidar"}` → `202`;
- `GET .../audio?voice=aidar` → `200`, 36 140 байт MP3;
- `POST .../audio {"voice":"xenia"}` → `202`;
- `GET .../audio?voice=xenia` → `200`, 33 068 байт MP3;
- `GET .../messages` → `audio_voices: [["aidar", "xenia"]]` у ответа;
- в Ceph найдено два объекта с разными `voice_id`;
- `DELETE /api/v1/dialogs/{dialog_id}` → `204`;
- после удаления объектов этого диалога в Ceph не осталось.

Legacy-запись `message_audio.audio_data` была перенесена в Ceph при старте:
`object_key` заполнен, `audio_data` очищен. Колонка оставлена nullable только
для обратной совместимости.

## Известные ограничения

- `ceph-rgw` использует образ `quay.io/s3gw/s3gw`, собранный под
  `linux/amd64`; на Apple Silicon требуется эмуляция Docker.
- Модель Silero v5 распространяется по некоммерческой лицензии.
- `audio_data` остаётся в схеме как legacy-поле, но новые записи его не
  используют.

## Критерии приёмки

- [x] В Compose есть внутренний `ceph-rgw` с томом `ceph-data`.
- [x] Новые MP3 сохраняются в Ceph, в PostgreSQL остаются метаданные.
- [x] Каждый `POST` запускает новую генерацию, старый MP3 доступен до успеха.
- [x] `GET messages` возвращает `audio_voices`.
- [x] Выбор голоса хранится в `localStorage`, меню без надписи «Голос».
- [x] Компактный плеер и кнопка скачивания работают по контракту.
- [x] `make test`, `make test-integration` и `make lint` проходят.
- [x] Документация обновлена.
