from pathlib import Path

import pytest

import smeshariki_ai.agent.prompts as prompts_module
from smeshariki_ai.agent.prompts import (
    SystemPromptResourceError,
    load_system_prompt,
)


class UnreadableResource:
    def joinpath(self, *descendants: str) -> "UnreadableResource":
        return self

    def read_text(self, encoding: str | None = None) -> str:
        raise OSError("private filesystem details")


def test_load_system_prompt_reads_trimmed_package_resource() -> None:
    prompt = load_system_prompt()

    assert prompt == prompt.strip()
    assert prompt
    assert all(
        name in prompt
        for name in ("get_story_canon", "lookup_knowledge", "search_lore")
    )


def test_load_system_prompt_does_not_depend_on_current_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    expected_prompt = load_system_prompt()
    monkeypatch.chdir(tmp_path)

    assert load_system_prompt() == expected_prompt


def test_load_system_prompt_rejects_blank_resource(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / "system.md").write_text(" \n\t", encoding="utf-8")
    monkeypatch.setattr(prompts_module.resources, "files", lambda _: tmp_path)

    with pytest.raises(
        SystemPromptResourceError,
        match="System prompt resource is empty",
    ):
        load_system_prompt()


def test_load_system_prompt_hides_resource_read_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        prompts_module.resources,
        "files",
        lambda _: UnreadableResource(),
    )

    with pytest.raises(
        SystemPromptResourceError,
        match="System prompt resource could not be read",
    ) as exc_info:
        load_system_prompt()

    assert "private filesystem details" not in str(exc_info.value)
