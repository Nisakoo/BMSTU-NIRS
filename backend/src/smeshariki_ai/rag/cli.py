from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import sys
from typing import Any

from pydantic import BaseModel, ValidationError

from smeshariki_ai.rag.git_store import (
    GitStructuredKnowledgeStore,
    StructuredKnowledgeLoadError,
)
from smeshariki_ai.rag.models import EntityType
from smeshariki_ai.rag.service import StructuredKnowledgeService


def _write_json(stream: Any, value: BaseModel | dict[str, str]) -> None:
    payload = value.model_dump(mode="json", by_alias=True) if isinstance(value, BaseModel) else value
    stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    stream.flush()


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the base RAG CLI")
    parser.add_argument("--context-path", type=Path)
    parser.add_argument("--knowledge-path", type=Path)
    return parser


def _create_store(arguments: argparse.Namespace) -> GitStructuredKnowledgeStore:
    if (arguments.context_path is None) != (arguments.knowledge_path is None):
        raise StructuredKnowledgeLoadError(
            "Both --context-path and --knowledge-path must be provided together"
        )
    if arguments.context_path is None:
        return GitStructuredKnowledgeStore.default()
    return GitStructuredKnowledgeStore(
        arguments.context_path,
        arguments.knowledge_path,
    )


def _invalid_command(message: str) -> dict[str, str]:
    return {"status": "error", "code": "invalid_command", "message": message}


def main(argv: list[str] | None = None) -> int:
    arguments = _argument_parser().parse_args(argv)
    try:
        service = StructuredKnowledgeService(_create_store(arguments))
    except StructuredKnowledgeLoadError as error:
        _write_json(
            sys.stderr,
            {
                "status": "error",
                "code": "knowledge_load_failed",
                "message": str(error),
            },
        )
        return 1

    _write_json(sys.stdout, {"status": "ready"})
    for raw_line in sys.stdin:
        try:
            tokens = shlex.split(raw_line)
        except ValueError as error:
            _write_json(sys.stdout, _invalid_command(str(error)))
            continue
        if not tokens:
            continue

        command = tokens[0]
        if command == "exit":
            if len(tokens) != 1:
                _write_json(sys.stdout, _invalid_command("exit takes no arguments"))
                continue
            return 0
        if command == "context":
            if len(tokens) != 1:
                _write_json(sys.stdout, _invalid_command("context takes no arguments"))
                continue
            _write_json(sys.stdout, service.get_system_context())
            continue
        if command == "lookup":
            if len(tokens) < 3:
                _write_json(
                    sys.stdout,
                    _invalid_command(
                        "usage: lookup <entity_type> <key> [canon_variants...]"
                    ),
                )
                continue
            try:
                entity_type = EntityType(tokens[1])
                result = service.lookup_knowledge(
                    entity_type,
                    tokens[2],
                    tuple(tokens[3:]),
                )
            except (ValueError, ValidationError) as error:
                _write_json(sys.stdout, _invalid_command(str(error)))
                continue
            _write_json(sys.stdout, result)
            continue

        _write_json(sys.stdout, _invalid_command(f"unknown command: {command}"))

    return 0
