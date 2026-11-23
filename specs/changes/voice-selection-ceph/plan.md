# План реализации выбора голоса и Ceph

## Связь со спецификацией

Реализуется `specs/changes/voice-selection-ceph/spec.md`. Изменение расширяет
`silero-narrator-tts`.

Ключевые решения:

- Ceph RGW через `quay.io/s3gw/s3gw` в Compose с внутренним портом `7480`;
- MP3 — в Ceph, метаданные — в PostgreSQL;
- голос выбирается на frontend и передаётся в API;
- каждый `POST` перегенерирует аудио;
- `message_audio` хранит запись по паре `(message_id, voice_id)`;
- старый объект не удаляется до успешной публикации нового.

## Риски

1. Образ s3gw собран под `linux/amd64`; на Apple Silicon нужна эмуляция
   Docker. Проверить запуск и загрузку объекта.
2. Существующая строка `message_audio` хранит `audio_data`; её нужно
   перенести в Ceph лениво, не потеряв старую озвучку.
3. Смена PK `message_audio` требует аккуратной миграции существующих строк.
4. Кастомный плеер должен работать в Node-тестах с текущим fake DOM.

## Задачи

### 1. Ceph-конфигурация и объектное хранилище

- Требования: REQ-020–REQ-025, REQ-030–REQ-031.
- Файлы:
  - `backend/src/smeshariki_ai/speech/objects.py`
  - `backend/src/smeshariki_ai/speech/ceph.py`
  - `backend/src/smeshariki_ai/speech/config.py`
  - `backend/tests/unit/speech/test_objects.py`
- Работа: `CephS3Config`, `AudioObjectStore`, `CephS3AudioObjectStore`,
  `InMemoryAudioObjectStore`, `put/get/delete`, path-style S3, bucket init.
- Проверка: `uv run --project backend --locked pytest backend/tests/unit/speech/test_objects.py`.

### 2. Схема `message_audio` и миграция

- Требования: REQ-021, REQ-022, REQ-026.
- Файлы:
  - `backend/src/smeshariki_ai/db/tables.py`
  - `backend/src/smeshariki_ai/db/migrations/versions/0014_message_audio_ceph.py`
  - `backend/tests/integration/db/test_postgres_audio.py`
- Работа: `voice_id`, `object_key`, `size_bytes`, `etag`, PK
  `(message_id, voice_id)`, сохранить `audio_data` nullable для backfill.
- Проверка: `make test-integration PYTEST_ARGS="backend/tests/integration/db/test_postgres_audio.py"`.

### 3. Контракт хранилища и in-memory реализация

- Требования: REQ-019–REQ-023, REQ-026–REQ-027.
- Файлы:
  - `backend/src/smeshariki_ai/speech/models.py`
  - `backend/src/smeshariki_ai/speech/store.py`
  - `backend/src/smeshariki_ai/speech/memory.py`
  - `backend/tests/unit/speech/test_audio_store.py`
- Работа: операции по `(message_id, voice_id)`, `ready_voices`,
  `legacy_records`, сохранение старого object key при `start`.
- Проверка: `uv run --project backend --locked pytest backend/tests/unit/speech/test_audio_store.py`.

### 4. PostgreSQL-хранилище

- Требования: REQ-021–REQ-023, REQ-026–REQ-027.
- Файлы:
  - `backend/src/smeshariki_ai/db/audio.py`
  - `backend/tests/integration/db/test_postgres_audio.py`
- Работа: реализация нового контракта, backfill legacy `audio_data`,
  `audio_voices`, восстановление `pending`.
- Проверка: целевой integration-тест из задачи 2.

### 5. Сервис озвучки и перегенерация

- Требования: REQ-014–REQ-019, REQ-026–REQ-027.
- Файлы:
  - `backend/src/smeshariki_ai/speech/service.py`
  - `backend/tests/unit/speech/test_service.py`
- Работа: голос в `request/get`, всегда новая генерация, generation id,
  Ceph put/delete, старый объект при ошибке, `audio_voices`.
- Проверка: `uv run --project backend --locked pytest backend/tests/unit/speech/test_service.py`.

### 6. HTTP API и bootstrap

- Требования: REQ-014–REQ-019, REQ-028–REQ-031.
- Файлы:
  - `backend/src/smeshariki_ai/api/schemas.py`
  - `backend/src/smeshariki_ai/api/app.py`
  - `backend/src/smeshariki_ai/bootstrap.py`
  - `backend/tests/integration/api/test_message_audio.py`
  - `backend/tests/unit/test_bootstrap.py`
- Работа: `AudioRequest`, `voice` в POST/GET, `audio_voices`, Ceph store в
  bootstrap, ручки без speech/Ceph — безопасный `503`.
- Проверка: `make test-integration PYTEST_ARGS="backend/tests/integration/api/test_message_audio.py"`.

### 7. Ceph в Docker Compose

- Требования: REQ-028–REQ-032.
- Файлы:
  - `docker/compose.yaml`
  - `docker/.env.example`
  - `docker/README.md`
- Работа: сервис `ceph-rgw`, том `ceph-data`, внутренний endpoint,
  `CEPH_S3_*`, `platform: linux/amd64` при необходимости.
- Проверка: `docker compose config`; загрузка/скачивание объекта вручную.

### 8. Frontend API и localStorage

- Требования: REQ-004–REQ-007, REQ-011–REQ-015.
- Файлы:
  - `frontend/src/agent-api.js`
  - `frontend/src/script.js`
  - `frontend/tests/agent-api.test.js`
- Работа: `voice` в `startAudio/getAudio/downloadAudio`, `audio_voices`,
  чтение/запись `smeshariki.voice`, default `aidar`.
- Проверка: `npm --prefix frontend test`.

### 9. Меню голоса, плеер и скачивание

- Требования: REQ-001–REQ-013.
- Файлы:
  - `frontend/src/script.js`
  - `frontend/src/styles.css`
  - `frontend/tests/ui.test.js`
- Работа: контрол «название + стрелка», popover с пятью голосами,
  клавиатура, кастомный компактный плеер, small download, regenerate.
- Проверка: `npm --prefix frontend test`.

### 10. Документация и итоговая проверка

- Требования: REQ-033.
- Файлы:
  - `docs/audio.md`
  - `docs/database.md`
  - `docs/configuration.md`
  - `docs/dialogs.md`
  - `docker/README.md`
  - `frontend/README.md`
  - `AGENTS.md`
- Проверка: `make lint`, `make test`, `make test-integration`, ручной
  Compose-сценарий с Ceph.
- После успешных проверок — `verification.md` и статус `done`.

## Порядок

1. Ceph config/object store.
2. Схема и хранилища.
3. Сервис.
4. API/bootstrap.
5. Compose Ceph.
6. Frontend API и UI.
7. Документация и проверка.
