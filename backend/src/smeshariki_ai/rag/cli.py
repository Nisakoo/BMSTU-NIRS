"""Knowledge commands: ``python -m smeshariki_ai.rag <command>``.

The commands are non-interactive, never read the environment and offer JSON
output, so the content author's agent can run them as well as a person.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from smeshariki_ai.rag.services import CheckReport, check_package, package_schema


def main(argv: Sequence[str] | None = None, stdout: TextIO = sys.stdout) -> int:
    parser = _parser()
    try:
        arguments = parser.parse_args(argv)
    except SystemExit as exit_:
        return int(exit_.code or 0)

    if arguments.command == "schema":
        _write_json(stdout, package_schema())
        return 0

    report = check_package(arguments.path)
    if arguments.format == "json":
        _write_json(stdout, report.model_dump(mode="json"))
    else:
        _write_text(stdout, report)
    return 0 if report.valid else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m smeshariki_ai.rag",
        description="Проверка пакетов структурированных знаний.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="проверить пакет без загрузки в БД")
    check.add_argument("path", type=Path, help="каталог пакета")
    check.add_argument("--format", choices=("text", "json"), default="text")
    commands.add_parser("schema", help="напечатать JSON Schema формата сущностей")
    return parser


def _write_json(stdout: TextIO, value: object) -> None:
    stdout.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _write_text(stdout: TextIO, report: CheckReport) -> None:
    for issue in report.issues:
        location = (
            issue.file if issue.line is None else f"{issue.file} (строка {issue.line})"
        )
        field = f" {issue.path}:" if issue.path else ""
        stdout.write(f"{location}:{field} {issue.message} [{issue.code}]\n")

    counts = ", ".join(f"{name}: {count}" for name, count in report.counts.items())
    stdout.write(f"Сущностей: {counts}\n")
    if report.external:
        references = ", ".join(f"{ref.type.value} {ref.id}" for ref in report.external)
        stdout.write(f"Внешние ссылки (проверяются при загрузке): {references}\n")
    if report.valid:
        stdout.write("Пакет валиден.\n")
    else:
        stdout.write(f"Ошибок: {len(report.issues)}\n")
