# Verification: зашифрованные данные RAG в репозитории

## Итог

Все требования и критерии приёмки `spec.md` подтверждены. Код продукта не
менялся; `make lint` и `make test` проходят.

## Окружение

- macOS (Darwin 25.3.0), uv 0.8.13, Python 3.12 (PEP 723 script),
  `cryptography==50.0.2` из `data_crypt.py.lock`.
- Прогоны скрипта — с `--root <временный каталог в scratchpad>` и
  синтетической фразой через `--passphrase-stdin`; настоящие `data/` и
  `encrypted/` не затрагивались. Временные каталоги удалены.

## Требования

| Требование | Проверка | Результат |
| --- | --- | --- |
| REQ-001 | `git check-ignore -v data/x` → `.gitignore:11:/data/`; `git check-ignore encrypted/data.enc` → код `1` | ✅ |
| REQ-002, REQ-006 | Round-trip синтетического каталога (кириллица и пробел в имени, пустая папка) и копии 32 реальных сценариев: `diff -r` без отличий | ✅ |
| REQ-003 | Фраза `short` → «Кодовая фраза короче 12 символов.», код `1`, хеш файла прежний; несовпадение повторного ввода (expect, TTY) → «Кодовые фразы не совпадают.», файл прежний; эхо ввода отсутствует | ✅ |
| REQ-004 | Повторное `encrypt` без изменений → «Данные не изменились…», хеш прежний; изменение одного файла → хеш изменился | ✅ |
| REQ-005 | `.DS_Store` и `.git` не восстанавливаются в свежую `data/`; символьная ссылка → ошибка; `data/` только с пустой папкой и `.DS_Store` → «пуста»; нет `data/` → «не найдена»; файл не создан | ✅ |
| REQ-007 | Неверная фраза и инвертированный байт шифртекста → «Неверная кодовая фраза или файл повреждён.», код `1`, `data/` не изменилась; мусор вместо файла → «не является архивом данных» | ✅ |
| REQ-008 | Изменённый и лишний файл → отказ со списком `data/a.txt`, `data/extra.txt`, код `1`; `--force` → `data/` совпадает с архивом, `.git` и `.DS_Store` верхнего уровня сохранены; совпадающая `data/` → «уже совпадает», код `0` | ✅ |
| REQ-009 | Ревью: `extractall(filter="data")` во временный каталог, предварительный отказ от абсолютных путей, `..` и элементов, кроме файлов и папок | ✅ |
| REQ-010 | `encrypt`/`decrypt` без TTY и флага, а также `make data-encrypt </dev/null` → «Нет терминала…», код `1`, файл не создан; `make -n` показывает вызов без `--passphrase-stdin` | ✅ |
| REQ-011 | Ревью сообщений; фраза не найдена ни в выводе прогонов, ни в `data.enc` | ✅ |
| REQ-012 | Ревью `.agents/skills/data-crypt/SKILL.md`: команды, сценарии, запрет агенту запрашивать, вводить и сохранять фразу | ✅ |
| REQ-013 | Ревью `AGENTS.md` (процесс разработки, «Реализованный каталог знаний» п. 2) и `docs/rag.md` (раздел «Данные») | ✅ |

## Команды

```sh
uv lock --script .agents/skills/data-crypt/scripts/data_crypt.py
uv run --locked --script .agents/skills/data-crypt/scripts/data_crypt.py --help
uv run --project backend --locked ruff check --config backend/pyproject.toml .agents/skills/data-crypt/scripts/data_crypt.py
uv run --project backend --locked ruff format --check --config backend/pyproject.toml .agents/skills/data-crypt/scripts/data_crypt.py
make help; make -n data-encrypt; make -n data-decrypt FORCE=1
make lint   # All checks passed, 151 files already formatted
make test   # frontend Node-тесты; backend: 815 passed, 125 skipped
```

Пропуски backend-тестов — интеграционные тесты без `TEST_DATABASE_URL`;
изменение их не затрагивает.

## Ограничения

- Интерактивный ввод через `make data-encrypt` / `make data-decrypt`
  проверяет пользователь своей фразой: агент её не вводит. Сам интерактивный
  путь `getpass` проверен через expect на синтетической фразе.
- `encrypted/data.enc` ещё не создан: его создаёт пользователь.
- При шифровании новой фразой поверх архива со старой скрипт только
  предупреждает и перезаписывает файл (по спецификации); вернуть прежний
  архив можно из Git.
- Skill лежит в `.agents/skills/`, как и `sdd`; в `.claude/skills/` он не
  добавлялся (по спецификации — только после согласования).
