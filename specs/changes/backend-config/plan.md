# План: единый корневой Config для backend

## Основание

План реализует одобренную спецификацию [`spec.md`](./spec.md) поверх
завершённых изменений `agent-runtime`, `agent-dialog-api` и
`litellm-provider`. Результат заменит смешанный `ApplicationConfig` на единый
immutable-агрегат `Config(agent=..., llm=...)`, оставив определения подконфигов
у соответствующих компонентов.

Перед планированием текущая реализация проверена командами `make test` и
`make lint`: проходят 88 тестов, Ruff не находит нарушений. Это базовая точка
для последующей реализации.

## Решения и зависимости

### Владение конфигурацией

`smeshariki_ai.config` остаётся одним файлом и единственной backend-wide точкой
загрузки внешней конфигурации. Он определяет только корневой `Config` и
`load_config`, импортируя принадлежащие компонентам `AgentConfig` и
`LiteLLMProviderConfig`.

Корневой объект имеет ровно два поля:

```python
class Config(BaseModel):
    agent: AgentConfig
    llm: LiteLLMProviderConfig
```

Все три модели остаются frozen и запрещают extra fields. Alias или временный
совместимый класс `ApplicationConfig` не вводится: все внутренние потребители
мигрируют атомарно в рамках изменения.

### Загрузка environment

`load_config(environ=None)` сохраняет явное преобразование существующих
`AGENT_*` и `LLM_*` значений. При `None` источником является `os.environ`, при
переданном `Mapping[str, str]` process environment не читается.

Loader сначала формирует отдельные значения для `AgentConfig` и
`LiteLLMProviderConfig`, затем собирает из готовых моделей `Config`. Defaults,
обязательность `LLM_MODEL`, blank-to-`None` для необязательных provider-полей и
Pydantic-валидация не меняются. Новый loader, singleton, dotenv-библиотека или
runtime dependency не добавляются.

### Composition root и entrypoint

Внешней границей загрузки становится `main.py`:

```python
app = create_application(load_config())
```

`create_application` требует готовый `Config`; bootstrap больше не импортирует
и не вызывает `load_config`. `build_agent_service` передаёт тот же экземпляр
`config.agent` в `Agent` и тот же экземпляр `config.llm` в
`LiteLLMProvider`. Явная подмена `LLMProvider` сохраняется, но не разрешает
опустить или обойти корневой config.

Тест entrypoint будет импортировать `smeshariki_ai.main` только после подмены
loader и application factory. Это поведенчески докажет один вызов загрузчика и
передачу того же `Config`, не создавая реальный LiteLLM-клиент и не завися от
process environment.

### Документация архитектуры

Новая страница `docs/configuration.md` описывает фактический поток
`environment -> load_config -> Config -> component configs`, границы владения и
правила добавления будущих подконфигов. `docs/README.md` включает страницу и
компонент в глобальную карту, а `AGENTS.md` закрепляет реализованные правила для
последующих изменений.

## Порядок реализации

1. Через TDD ввести корневой `Config` и перенести loader на вложенные
   component-owned модели.
2. Через TDD сделать bootstrap чистым composition root и перенести единственную
   загрузку в ASGI-entrypoint.
3. Документировать общий конфигурационный контракт и архитектурные границы.
4. Выполнить полную проверку требований перед этапом `verify`.

Первые две задачи закрывают основные риски: сохранение environment-контракта,
отсутствие скрытого чтения и передачу точных экземпляров подконфигов.

## Задача 1. Ввести Config и вложенную загрузку

**Связанные требования:** REQ-001–REQ-008, REQ-013–REQ-015.

**Критерии приёмки:** публичный модуль предоставляет только один корневой тип
`Config`; loader возвращает `Config(agent=..., llm=...)`, сохраняет все
действующие environment names/defaults/validation и не читает process
environment при явном mapping; корень и оба подконфига immutable; секрет не
раскрывается; повторные загрузки независимы; новых зависимостей нет.

**Зависимости:** нет.

**Файлы:**

- `backend/src/smeshariki_ai/config.py`;
- `backend/tests/unit/test_backend_config.py`;
- `backend/tests/unit/test_bootstrap.py`.

**Действия (RED -> GREEN -> REFACTOR):**

1. Перенести loader-тесты из bootstrap-набора в отдельный поведенческий набор
   `test_backend_config.py` и сначала обновить их под публичный `Config`.
2. Добавить падающие тесты точного состава полей, extra-forbid/frozen на
   корне и вложенных моделях, отсутствия `ApplicationConfig`, маскирования
   секрета, двух независимых загрузок и запрета чтения `os.environ` при явном
   mapping.
3. Заменить `ApplicationConfig` на `Config(agent, llm)` без совместимого alias.
4. Перестроить `load_config`, создавая `AgentConfig` и
   `LiteLLMProviderConfig` с прежними defaults и правилами преобразования.
5. Проверить поиском, что вне `config.py` нет чтения environment и что
   dependency/lock-файлы не изменились.

**Тест:**

```sh
uv run --project backend --locked pytest backend/tests/unit/test_backend_config.py
```

## Задача 2. Очистить bootstrap и перенести загрузку в entrypoint

**Связанные требования:** REQ-009–REQ-015, REQ-017.

**Критерии приёмки:** `main.py` один раз загружает и передаёт готовый `Config`;
`create_application` требует config и не имеет скрытого loader/default;
bootstrap передаёт точные экземпляры `config.agent` и `config.llm`; explicit
provider override работает только вместе с валидным config; HTTP API, agent
loop и provider behavior не меняются.

**Зависимости:** задача 1.

**Файлы:**

- `backend/src/smeshariki_ai/bootstrap.py`;
- `backend/src/smeshariki_ai/main.py`;
- `backend/tests/unit/test_bootstrap.py`.

**Действия (RED -> GREEN -> REFACTOR):**

1. Обновить bootstrap-тесты на обязательный `Config` и добавить проверку, что
   вызов без него отклоняется сигнатурой, а не запускает loader или defaults.
2. Подменами конструкторов доказать identity-передачу `config.agent` в `Agent`
   и `config.llm` в `LiteLLMProvider`, включая ветку явного fake provider.
3. Добавить изолированный тест импорта `main.py`, который считает вызовы
   `load_config`, перехватывает аргумент `create_application` и не обращается к
   реальной модели или сети.
4. Изменить bootstrap на обязательный `Config`, удалить импорт loader и
   повторную сборку `AgentConfig` из плоских полей.
5. Изменить entrypoint на `create_application(load_config())` и прогнать
   интеграционные API-тесты для подтверждения отсутствия HTTP-регрессии.

**Тест:**

```sh
uv run --project backend --locked pytest backend/tests/unit/test_bootstrap.py backend/tests/integration/api/test_dialogs.py
```

## Задача 3. Документировать общий конфигурационный контракт

**Связанные требования:** REQ-003, REQ-004, REQ-008–REQ-016.

**Критерии приёмки:** архитектурный каталог описывает единую точку загрузки,
корневой aggregate без singleton, component ownership и поток передачи
подконфигов; глобальная карта ссылается на реализацию и SDD-артефакты;
`AGENTS.md` закрепляет правила для будущего backend-кода без копирования всей
спецификации.

**Зависимости:** задачи 1–2, чтобы документация описывала фактическую
реализацию.

**Файлы:**

- `docs/configuration.md`;
- `docs/README.md`;
- `docs/agent.md`;
- `AGENTS.md`.

**Действия:**

1. Создать тематическую страницу с публичным контрактом `Config`/`load_config`,
   таблицей текущих переменных и правилами владения подконфигами.
2. Добавить компактную Mermaid-схему потока только там, где она поясняет
   архитектурную границу.
3. Обновить тематический список, архитектурную карту и таблицу компонентов в
   `docs/README.md`.
4. Исправить ссылку на источник provider-конфигурации в `docs/agent.md`, чтобы
   тематические страницы не описывали bootstrap как environment reader.
5. Дополнить раздел согласованной/реализованной архитектуры в `AGENTS.md`
   правилами единственного environment reader и передачи только подконфигов.
6. Проверить ссылки и соответствие фактическим именам модулей вручную; не
   добавлять структурные тесты документации.

**Проверка:** ревью `docs/configuration.md`, `docs/README.md`, `docs/agent.md`
и `AGENTS.md`, а также `git diff --check`.

## Задача 4. Полная проверка реализации

**Связанные требования:** REQ-001–REQ-017.

**Критерии приёмки:** все целевые и регрессионные тесты проходят без сети;
Ruff не находит нарушений; нет `ApplicationConfig`, посторонних environment
reads, config singleton, новых зависимостей или изменений Docker/environment
контракта; diff соответствует спецификации и готов к отдельному этапу verify.

**Зависимости:** задачи 1–3.

**Файлы:** изменения не планируются; исправления возвращаются в задачу,
нарушившую проверку.

**Проверка:**

```sh
make test
make lint
git diff --check
```

Дополнительно ревью через `rg` подтверждает отсутствие `ApplicationConfig`,
чтения `os.environ` вне `smeshariki_ai.config` и импортов корневого `Config`
внутри agent/provider/API/application/dialogs. Сравнение diff для
`backend/pyproject.toml`, `backend/uv.lock` и `docker/` подтверждает отсутствие
несогласованных изменений.

## Трассировка требований

| Требование | Задачи | Доказательство |
| --- | --- | --- |
| REQ-001–REQ-003 | 1, 3 | Публичная модель, ownership-тесты и архитектурная документация |
| REQ-004–REQ-008 | 1 | Unit-тесты loader, validation, immutable state и secret redaction |
| REQ-009–REQ-012 | 2 | Unit-тесты entrypoint/bootstrap и identity dependency injection |
| REQ-013–REQ-015 | 1, 2, 4 | Поведенческие тесты, ревью импортов/environment reads и dependency diff |
| REQ-016 | 3 | Ревью тематической страницы, глобальной карты и `AGENTS.md` |
| REQ-017 | 1, 2, 4 | Целевые pytest-команды, `make test` и `make lint` |

## Риски и откат

- Импорт `main.py` создаёт ASGI-приложение немедленно. Тест изолирует импорт и
  удаляет временный модуль из `sys.modules`, чтобы порядок запуска тестов не
  скрывал или дублировал загрузку.
- Удаление `ApplicationConfig` намеренно ломает внутреннее старое имя. Все
  использования мигрируют одной задачей; публичного backward-compatibility
  контракта для него нет.
- Ошибка при старте после переноса loader проявится на импорте ASGI entrypoint,
  что является требуемым fail-fast поведением. Unit-тесты bootstrap используют
  готовый config и не зависят от process environment.
- Откат выполняется возвратом изменений `config.py`, bootstrap/entrypoint и их
  тестов как одной атомарной группы; environment и Docker-файлы не требуют
  миграции данных или обратного изменения.
