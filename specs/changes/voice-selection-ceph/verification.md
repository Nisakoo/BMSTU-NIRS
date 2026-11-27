# Проверка выбора голоса и Ceph

Исторический оригинал: `git show 5af56b5:specs/changes/voice-selection-ceph/verification.md`.

## Результат

- Изменение реализовано. Выбор голоса хранится во frontend, каждый запрос озвучки перегенерирует MP3, файлы лежат в Ceph, метаданные — в PostgreSQL.
- Команды: `make lint` — успешно, форматирование проверено
- Команды: `make test` — 931 passed, 129 skipped (PostgreSQL/Redis без env)
- Команды: `make test-integration` — 1060 passed
- Команды: `docker compose --env-file docker/.env -f docker/compose.yaml up -d --build --wait` — все сервисы healthy, включая `ceph-rgw`
- Команды: `GET /` на `127.0.0.1:8090` — `200`
- `ceph-rgw` использует образ `quay.io/s3gw/s3gw`, собранный под `linux/amd64`; на Apple Silicon требуется эмуляция Docker.
- Модель Silero v5 распространяется по некоммерческой лицензии.
- `audio_data` остаётся в схеме как legacy-поле, но новые записи его не используют.
