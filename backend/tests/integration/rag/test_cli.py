from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def run_cli(
    commands: str,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "smeshariki_ai.rag", *arguments],
        input=commands,
        text=True,
        capture_output=True,
        check=False,
    )


def test_cli_exposes_context_and_all_lookup_statuses() -> None:
    completed = run_cli(
        "\n".join(
            (
                "context",
                'lookup character "Пин"',
                'lookup character "Пин" movie',
                'lookup location "мастерская пина"',
                "lookup character неизвестный",
                "exit",
            )
        )
        + "\n"
    )

    assert completed.returncode == 0, completed.stderr
    messages = [json.loads(line) for line in completed.stdout.splitlines()]
    assert messages[0] == {"status": "ready"}
    assert messages[1]["version"] == "1"
    assert messages[2]["status"] == "ambiguous"
    assert messages[3]["status"] == "found"
    assert messages[3]["entity"]["id"] == "pin_movie"
    assert messages[4]["status"] == "found"
    assert messages[4]["entity"]["id"] == "pin_house"
    assert messages[5]["status"] == "not_found"


def test_cli_reports_command_errors_and_continues() -> None:
    completed = run_cli("unknown\ncontext\nexit\n")

    assert completed.returncode == 0
    messages = [json.loads(line) for line in completed.stdout.splitlines()]
    assert messages[1]["status"] == "error"
    assert messages[1]["code"] == "invalid_command"
    assert messages[2]["version"] == "1"


def test_cli_fails_before_ready_when_sources_are_invalid(tmp_path: Path) -> None:
    context = tmp_path / "context.md"
    knowledge = tmp_path / "knowledge.json"
    context.write_text("invalid context", encoding="utf-8")
    knowledge.write_text('{"schema_version":"1","records":[]}', encoding="utf-8")

    completed = run_cli(
        "",
        "--context-path",
        str(context),
        "--knowledge-path",
        str(knowledge),
    )

    assert completed.returncode != 0
    assert completed.stdout == ""
    error = json.loads(completed.stderr)
    assert error["status"] == "error"
    assert error["code"] == "knowledge_load_failed"
