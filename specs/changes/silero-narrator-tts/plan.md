# План реализации Silero v5 narrator TTS

## Связь со спецификацией

Реализуется `specs/changes/silero-narrator-tts/spec.md`.

Основные решения плана:

- локальный Silero v5, один голос рассказчика, без разметки ролей;
- озвучка по требованию для сохранённого ответа ассистента;
- `POST` запускает фоновую генерацию, `GET` отдаёт статус или MP3;
- готовое аудио хранится в PostgreSQL в `message_audio`;
- после готовности кнопка «Озвучить» заменяется на «Скачать»;
- `GET /messages` возвращает `audio_available`, чтобы сохранённая история
  сразу показывала «Скачать»;
- в тестах используется fake-провайдер и fake-кодировщик, реальная модель
  проверяется отдельно вручную.

## Риски и предположения

1. **Silero v5 URL и checksum.** В текущем окружении официальный CDN Silero
   недоступен, поэтому точный URL и SHA-256 нужно подтвердить при реализации
   задачи загрузки модели. Если подтвердить не удастся, реализация
   останавливается и уточняет источник у владельца проекта.
2. **CPU-зависимости.** `torch` нужно ставить из CPU-индекса, иначе образ
   вырастет из-за CUDA-пакетов. Изменение `uv.lock` может быть тяжёлым по
   времени.
3. **MP3-кодирование.** Для production-кодирования используется `ffmpeg`,
   устанавливаемый в Docker-образ. В тестах кодировщик подменяется
   детерминированной реализацией, чтобы `make test` не зависел от бинарника.
4. **`audio_available` меняет контракт `GET /messages`.** Поле добавляется
   как новое, старые ответы без него не должны ломать frontend.
5. **Модель не коммитится.** В Git попадают только скрипт загрузки, URL,
   версия и checksum; веса Silero v5 остаются вне репозитория.
6. **Отключение озвучки.** `SPEECH_ENABLED=false` позволяет запускать backend
   без модели; при этом ручки аудио отвечают `503`, а `audio_available` всегда
   `false`. Это нужно для тестов и окружений без модели.

## Задачи

### 1. Доменные модели и конфигурация `SpeechConfig`

- Требования: REQ-001, REQ-002, REQ-009, REQ-015, REQ-023, REQ-024.
- Зависимости: нет.
- Файлы:
  - `backend/src/smeshariki_ai/speech/__init__.py`
  - `backend/src/smeshariki_ai/speech/config.py`
  - `backend/src/smeshariki_ai/speech/models.py`
  - `backend/tests/unit/speech/test_config.py`
- Работа:
  - immutable `SpeechConfig` с `enabled`, `voice`, `speed`,
    `max_concurrency`, `max_text_chars`, `model_path`;
  - статусы `pending`/`ready`/`failed` и модели аудиозаписи;
  - версия голоса как строка, включающая модель, голос, скорость и версию
    нормализации.
- Проверка:
  `uv run --project backend --locked pytest backend/tests/unit/speech/test_config.py`.

### 2. Интеграция `SpeechConfig` в корневой `Config`

- Требования: REQ-023, REQ-024, REQ-025.
- Зависимости: задача 1.
- Файлы:
  - `backend/src/smeshariki_ai/config.py`
  - `backend/tests/unit/test_backend_config.py`
- Работа:
  - корневой `Config` получает `speech: SpeechConfig`;
  - `load_config` читает `SPEECH_ENABLED`, `SPEECH_VOICE`, `SPEECH_SPEED`,
    `SPEECH_MAX_CONCURRENCY`, `SPEECH_MAX_TEXT_CHARS`, `SPEECH_MODEL_PATH`;
  - невалидные значения и неизвестные поля отклоняются;
  - тестовые `Config` без speech получают явное безопасное значение.
- Проверка:
  `uv run --project backend --locked pytest backend/tests/unit/test_backend_config.py`.

### 3. Нормализация и нарезка текста

- Требования: REQ-004, REQ-005.
- Зависимости: задача 1.
- Файлы:
  - `backend/src/smeshariki_ai/speech/normalize.py`
  - `backend/tests/unit/speech/test_normalize.py`
- Работа:
  - нормализация пробелов, кавычек, тире и случайного Markdown;
  - нарезка по предложениям/абзацам с лимитом;
  - паузы между абзацами;
  - отсутствие потерь и дублей.
- Проверка:
  `uv run --project backend --locked pytest backend/tests/unit/speech/test_normalize.py`.

### 4. Получение конкретного сообщения из истории

- Требования: REQ-017, REQ-020, REQ-036.
- Зависимости: нет.
- Файлы:
  - `backend/src/smeshariki_ai/dialogs/history.py`
  - `backend/src/smeshariki_ai/db/history.py`
  - `backend/tests/unit/dialogs/test_history.py`
  - `backend/tests/integration/db/test_postgres_history.py`
- Работа:
  - `HistoryStore.get_message(owner_id, dialog_id, message_id)` возвращает
    `StoredMessage` только для сообщения своего диалога;
  - для чужого/несуществующего/пользовательского сообщения —
    `MessageNotFoundError`;
  - PostgreSQL-реализация проверяет владельца и роль в одном запросе.
- Проверка:
  `uv run --project backend --locked pytest backend/tests/unit/dialogs/test_history.py`
  и `make test-integration PYTEST_ARGS="backend/tests/integration/db/test_postgres_history.py"`.

### 5. Контракт хранилища аудио и in-memory реализация

- Требования: REQ-008, REQ-010, REQ-011, REQ-012, REQ-022, REQ-036.
- Зависимости: задача 1.
- Файлы:
  - `backend/src/smeshariki_ai/speech/store.py`
  - `backend/src/smeshariki_ai/speech/memory.py`
  - `backend/tests/unit/speech/test_audio_store.py`
- Работа:
  - `MessageAudioStore` с операциями `get`, `start`, `complete`, `fail`,
    `reset_pending`, `ready_message_ids`;
  - идемпотентный `start`: готовое актуальное аудио не перезаписывается,
    `pending` не создаёт вторую задачу;
  - in-memory реализация для unit-тестов и API-тестов.
- Проверка:
  `uv run --project backend --locked pytest backend/tests/unit/speech/test_audio_store.py`.

### 6. PostgreSQL-хранилище аудио и миграция

- Требования: REQ-010, REQ-011, REQ-012, REQ-022, REQ-036.
- Зависимости: задачи 2, 5.
- Файлы:
  - `backend/src/smeshariki_ai/db/audio.py`
  - `backend/src/smeshariki_ai/db/tables.py`
  - `backend/src/smeshariki_ai/db/__init__.py`
  - `backend/src/smeshariki_ai/db/migrations/versions/0013_message_audio.py`
  - `backend/tests/integration/db/test_postgres_audio.py`
- Работа:
  - таблица `message_audio` с PK `message_id`, FK на `messages` с
    `ON DELETE CASCADE`, статусами и `BYTEA`;
  - `PostgresMessageAudioStore` с теми же операциями, что in-memory;
  - проверка каскадного удаления и восстановления после `pending`.
- Проверка:
  `make test-integration PYTEST_ARGS="backend/tests/integration/db/test_postgres_audio.py"`.

### 7. Контракт TTS-провайдера, fake-провайдер и кодировщик

- Требования: REQ-001, REQ-006, REQ-014, REQ-015.
- Зависимости: задача 1.
- Файлы:
  - `backend/src/smeshariki_ai/speech/provider.py`
  - `backend/src/smeshariki_ai/speech/fake.py`
  - `backend/src/smeshariki_ai/speech/encoder.py`
  - `backend/tests/unit/speech/test_provider.py`
- Работа:
  - асинхронный `SpeechProvider.synthesize(text, voice)` возвращает WAV;
  - fake-провайдер возвращает детерминированный WAV и фиксирует вызовы;
  - `AudioEncoder.to_mp3(wav)` и production-реализация через `ffmpeg`;
  - безопасные ошибки без текста и аудио.
- Проверка:
  `uv run --project backend --locked pytest backend/tests/unit/speech/test_provider.py`.

### 8. Silero v5-провайдер и загрузка модели

- Требования: REQ-001, REQ-002, REQ-003, REQ-014, REQ-026.
- Зависимости: задача 7.
- Файлы:
  - `backend/src/smeshariki_ai/speech/silero.py`
  - `docker/fetch-silero.sh`
  - `backend/tests/unit/speech/test_silero.py`
- Работа:
  - загрузка `v5_ru.pt` через `torch.package.PackageImporter`;
  - CPU-инференс `apply_tts` и преобразование результата в WAV;
  - проверка голоса по `model.speakers`;
  - версия модели по хэшу файла;
  - скрипт загрузки с pinned URL, `SHA-256` и offline-режимом.
- Проверка:
  `uv run --project backend --locked pytest backend/tests/unit/speech/test_silero.py`.
- Блокирующий риск: если URL/checksum v5 не подтверждаются, остановиться и
  уточнить у владельца.

### 9. `NarratorSpeechService`

- Требования: REQ-006, REQ-007, REQ-008, REQ-009, REQ-012, REQ-013, REQ-014,
  REQ-015, REQ-022.
- Зависимости: задачи 3–8.
- Файлы:
  - `backend/src/smeshariki_ai/speech/service.py`
  - `backend/src/smeshariki_ai/speech/errors.py`
  - `backend/tests/unit/speech/test_service.py`
- Работа:
  - проверка сообщения через `HistoryStore.get_message`;
  - кэш и идемпотентность;
  - фоновые задачи, per-message lock, общий семафор CPU;
  - нормализация → синтез в потоке → MP3 → `complete`;
  - `fail`, отмена, shutdown;
  - `available_message_ids` для `audio_available`.
- Проверка:
  `uv run --project backend --locked pytest backend/tests/unit/speech/test_service.py`.

### 10. HTTP-контракт аудио и `audio_available`

- Требования: REQ-017–REQ-022, REQ-036, REQ-037.
- Зависимости: задачи 6, 9.
- Файлы:
  - `backend/src/smeshariki_ai/api/app.py`
  - `backend/src/smeshariki_ai/api/schemas.py`
  - `backend/tests/integration/api/test_message_audio.py`
  - `backend/tests/integration/api/test_dialog_history.py`
- Работа:
  - `POST`/`GET /api/v1/dialogs/{dialog_id}/messages/{message_id}/audio`;
  - `?download=1` и `Content-Disposition`;
  - проверка владельца и роли;
  - `202`/`200`/`404`/`503`;
  - `audio_available` в `GET /messages`.
- Проверка:
  `make test-integration PYTEST_ARGS="backend/tests/integration/api/test_message_audio.py backend/tests/integration/api/test_dialog_history.py"`.

### 11. Bootstrap, конфигурация и отключённый режим

- Требования: REQ-001, REQ-003, REQ-023–REQ-026.
- Зависимости: задачи 2, 6, 9, 10.
- Файлы:
  - `backend/src/smeshariki_ai/bootstrap.py`
  - `backend/tests/unit/test_bootstrap.py`
- Работа:
  - production bootstrap создаёт `PostgresMessageAudioStore`,
    `SileroSpeechProvider`, `FfmpegAudioEncoder` и `NarratorSpeechService`;
  - при `SPEECH_ENABLED=false` создаётся недоступный сервис без загрузки
    модели;
  - `create_app` получает сервис озвучки;
  - startup сбрасывает `pending`, shutdown отменяет задачи.
- Проверка:
  `uv run --project backend --locked pytest backend/tests/unit/test_bootstrap.py`.

### 12. Python-зависимости, Docker и переменные окружения

- Требования: REQ-024–REQ-026.
- Зависимости: задачи 8, 11.
- Файлы:
  - `backend/pyproject.toml`
  - `backend/uv.lock`
  - `docker/Dockerfile`
  - `docker/compose.yaml`
  - `docker/.env.example`
  - `docker/fetch-silero.sh` (уточнение после задачи 8)
- Работа:
  - `torch` CPU, `numpy` при необходимости, `ffmpeg` в образе;
  - pinned модель и проверка checksum;
  - переменные `SPEECH_*` в Compose и примере;
  - `docker/models/` исключается из Git.
- Проверка:
  `make lint`; ревью Dockerfile и Compose; при наличии модели — `make run`.

### 13. Frontend API-клиент

- Требования: REQ-027, REQ-028, REQ-032, REQ-037.
- Зависимости: задача 10.
- Файлы:
  - `frontend/src/agent-api.js`
  - `frontend/tests/agent-api.test.js`
- Работа:
  - методы `startAudio`, `getAudio`, `downloadAudio`;
  - обработка `202`, `200`, `401`, `404`, `503`;
  - `download=1` и blob-скачивание.
- Проверка:
  `npm --prefix frontend test`.

### 14. Frontend UI: «Озвучить» → «Скачать»

- Требования: REQ-027–REQ-033, REQ-037.
- Зависимости: задача 13.
- Файлы:
  - `frontend/src/script.js`
  - `frontend/src/styles.css`
  - `frontend/tests/ui.test.js`
- Работа:
  - кнопка у завершённого ответа;
  - polling и состояние «Готовим озвучку…»;
  - `<audio controls>` и замена кнопки на «Скачать»;
  - отображение «Скачать» для `audio_available`;
  - остановка аудио и polling при переключении истории;
  - безопасные ошибки и `withSession`.
- Проверка:
  `npm --prefix frontend test`.

### 15. Документация

- Требования: REQ-034, REQ-035.
- Зависимости: задачи 10–14.
- Файлы:
  - `docs/audio.md`
  - `docs/README.md`
  - `docs/dialogs.md`
  - `docs/database.md`
  - `docs/configuration.md`
  - `docker/README.md`
  - `frontend/README.md`
  - `AGENTS.md`
- Работа: описать компонент, API, схему `message_audio`, настройки, модель,
  кнопку «Озвучить»/«Скачать» и ограничения CPU.
- Проверка: ревью документации; автоматические тесты структуры не добавлять.

### 16. Итоговая проверка

- Зависимости: все задачи.
- Команды:
  - `make test`
  - `make lint`
  - `make test-integration`
  - ручная проверка `make run`, если доступна модель Silero v5.
- Результат: заполнить `specs/changes/silero-narrator-tts/verification.md`
  только после успешных проверок. До этого статус остаётся `in-progress`.

## Порядок выполнения

1. Задачи 1–3.
2. Задачи 4–6.
3. Задачи 7–9.
4. Задачи 10–12.
5. Задачи 13–14.
6. Задача 15.
7. Задача 16.

После каждой задачи с Python-кодом запускается указанная команда. Если
появляется вопрос по URL/checksum модели, голосу, формату MP3 или контракту
`audio_available`, реализация останавливается до ответа владельца.
