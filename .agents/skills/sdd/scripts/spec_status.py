"""Manage the SDD specification status registry."""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


VALID_STATUSES = ("draft", "in-queue", "in-progress", "done")
NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
NAME_LINE_PATTERN = re.compile(r"^    - name: ([A-Za-z0-9][A-Za-z0-9._-]*)$")
STATUS_LINE_PATTERN = re.compile(
    r"^      status: (draft|in-queue|in-progress|done)$"
)


class RegistryError(Exception):
    """Raised when the registry or a requested mutation is invalid."""


@dataclass(frozen=True)
class SpecStatus:
    name: str
    status: str


def repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def registry_path() -> Path:
    return repository_root() / "specs" / "status.yaml"


def validate_name(name: str) -> None:
    if not NAME_PATTERN.fullmatch(name):
        raise RegistryError(
            "specification name must match [A-Za-z0-9][A-Za-z0-9._-]*"
        )


def load_registry(path: Path) -> list[SpecStatus]:
    if not path.exists():
        return []

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as error:
        raise RegistryError(f"cannot read {path}: {error}") from error

    lines = content.splitlines()
    if lines == ["specs: []"]:
        return []
    if not lines or lines[0] != "specs:" or len(lines) == 1:
        raise RegistryError(f"{path} does not match the managed registry format")

    entries: list[SpecStatus] = []
    seen_names: set[str] = set()
    index = 1
    while index < len(lines):
        if index + 1 >= len(lines):
            raise RegistryError(f"{path} contains an incomplete specification entry")

        name_match = NAME_LINE_PATTERN.fullmatch(lines[index])
        status_match = STATUS_LINE_PATTERN.fullmatch(lines[index + 1])
        if name_match is None or status_match is None:
            raise RegistryError(f"{path} does not match the managed registry format")

        name = name_match.group(1)
        status = status_match.group(1)
        if name in seen_names:
            raise RegistryError(f"{path} contains duplicate specification {name!r}")

        seen_names.add(name)
        entries.append(SpecStatus(name=name, status=status))
        index += 2

    return entries


def serialize_registry(entries: Sequence[SpecStatus]) -> str:
    if not entries:
        return "specs: []\n"

    lines = ["specs:"]
    for entry in entries:
        lines.append(f"    - name: {entry.name}")
        lines.append(f"      status: {entry.status}")
    return "\n".join(lines) + "\n"


def write_registry(path: Path, entries: Sequence[SpecStatus]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=".status.yaml.",
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
            file.write(serialize_registry(entries))
            file.flush()
            os.fsync(file.fileno())
        os.chmod(temporary_path, existing_mode)
        os.replace(temporary_path, path)
    except OSError as error:
        raise RegistryError(f"cannot write {path}: {error}") from error
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def create_entry(path: Path, name: str, status: str) -> None:
    validate_name(name)
    entries = load_registry(path)
    if any(entry.name == name for entry in entries):
        raise RegistryError(f"specification {name!r} already exists")

    entries.append(SpecStatus(name=name, status=status))
    write_registry(path, entries)
    print(f"Created {name} with status {status}.")


def update_entry(path: Path, name: str, status: str) -> None:
    validate_name(name)
    entries = load_registry(path)
    if not any(entry.name == name for entry in entries):
        raise RegistryError(f"specification {name!r} does not exist")

    updated = [
        SpecStatus(name=entry.name, status=status)
        if entry.name == name
        else entry
        for entry in entries
    ]
    write_registry(path, updated)
    print(f"Updated {name} to status {status}.")


def delete_entry(path: Path, name: str) -> None:
    validate_name(name)
    entries = load_registry(path)
    if not any(entry.name == name for entry in entries):
        raise RegistryError(f"specification {name!r} does not exist")

    remaining = [entry for entry in entries if entry.name != name]
    write_registry(path, remaining)
    print(f"Deleted {name} from the registry.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create, update, or delete an SDD specification status."
    )
    subparsers = parser.add_subparsers(dest="operation", required=True)

    create_parser = subparsers.add_parser("create", help="create a registry entry")
    create_parser.add_argument("name")
    create_parser.add_argument(
        "--status",
        choices=VALID_STATUSES,
        default="draft",
    )

    update_parser = subparsers.add_parser("update", help="update an entry status")
    update_parser.add_argument("name")
    update_parser.add_argument("status", choices=VALID_STATUSES)

    delete_parser = subparsers.add_parser("delete", help="delete a registry entry")
    delete_parser.add_argument("name")

    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    path = registry_path()
    try:
        if arguments.operation == "create":
            create_entry(path, arguments.name, arguments.status)
        elif arguments.operation == "update":
            update_entry(path, arguments.name, arguments.status)
        else:
            delete_entry(path, arguments.name)
    except RegistryError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
