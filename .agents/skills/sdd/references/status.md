# Status

`specs/status.yaml` — краткий реестр SDD-изменений. Читать его можно напрямую,
но создавать, обновлять и удалять записи разрешено только скриптом
`.agents/skills/sdd/scripts/spec_status.py`.

Не изменяй реестр через `apply_patch`, редактор, shell redirect или форматтер.
Прогресс задач, описания, даты и другие поля в реестр не добавляй.

## Формат

```yaml
specs:
    - name: SPEC-1
      status: draft
```

Допустимые статусы:

- `draft` — спецификация ещё не закончена или не согласована;
- `in-queue` — спецификация согласована и ожидает продолжения;
- `in-progress` — по спецификации сейчас идёт активная работа;
- `done` — успешный verify завершён и записан `verification.md`.

## Команды

Запускай из корня репозитория:

```sh
uv run --no-project python .agents/skills/sdd/scripts/spec_status.py create SPEC-1
uv run --no-project python .agents/skills/sdd/scripts/spec_status.py create SPEC-2 --status in-queue
uv run --no-project python .agents/skills/sdd/scripts/spec_status.py update SPEC-1 in-progress
uv run --no-project python .agents/skills/sdd/scripts/spec_status.py delete SPEC-1
```

Create добавляет только запись и использует `draft` по умолчанию. Update меняет
только статус. Delete удаляет только запись из реестра и никогда не удаляет
`specs/changes/<change-id>/` или другие файлы.

## Переходы процесса

1. Начало новой спецификации: Create с `draft`.
2. Явное одобрение законченной спецификации: Update в `in-queue`.
3. Начало plan, implement или verify: Update в `in-progress`.
4. Остановка активной работы в ожидании продолжения: Update в `in-queue`.
5. Успешный verify и созданный `verification.md`: Update в `done`.

Не понижай обычным Update корректный `done`: изменение завершённого поведения
оформляй новым change-id. Если реестр повреждён или не соответствует схеме, не
редактируй его вручную — остановись и сообщи о проблеме.
