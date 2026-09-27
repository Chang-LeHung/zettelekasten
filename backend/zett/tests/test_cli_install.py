"""`zett install` writes the Zett skill where a coding agent reads skills."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zett.cli import main
from zett.infra.skills import coding_agents
from zett.infra.skills.coding_agents import CLI_SKILL, CLI_SKILL_NAME, CODING_AGENTS, CodingAgent

SKILL_RELATIVE_PATH = Path(CLI_SKILL_NAME) / "SKILL.md"


def test_install_writes_the_skill_below_the_skill_root(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["install", "--dir", str(tmp_path)]) == 0

    path = tmp_path / SKILL_RELATIVE_PATH
    assert path.is_file()
    assert path.read_text(encoding="utf-8") == CLI_SKILL
    # The frontmatter names the skill exactly as its directory does, because the
    # agent indexes it by that name.
    assert CLI_SKILL.startswith(f"---\nname: {CLI_SKILL_NAME}\n")
    assert f"Installed the Zett skill for custom: {path}" in capsys.readouterr().out


def test_install_leaves_an_identical_skill_file_untouched(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Running it twice is a no-op, down to the file's timestamp."""
    assert main(["install", "--dir", str(tmp_path)]) == 0
    path = tmp_path / SKILL_RELATIVE_PATH
    written_at = path.stat().st_mtime_ns

    assert main(["install", "--dir", str(tmp_path)]) == 0

    assert path.stat().st_mtime_ns == written_at
    assert f"The Zett skill is already installed for custom: {path}" in capsys.readouterr().out


def test_install_refuses_to_replace_an_edited_skill(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """An agent owner's edits are theirs; replacing them takes --force."""
    path = tmp_path / SKILL_RELATIVE_PATH
    path.parent.mkdir(parents=True)
    path.write_text("my own instructions\n", encoding="utf-8")

    assert main(["install", "--dir", str(tmp_path)]) == 1

    captured = capsys.readouterr()
    assert "differs from the shipped skill" in captured.err
    assert "--force" in captured.err
    assert captured.out == ""
    assert path.read_text(encoding="utf-8") == "my own instructions\n"


def test_install_force_replaces_an_edited_skill(tmp_path: Path) -> None:
    path = tmp_path / SKILL_RELATIVE_PATH
    path.parent.mkdir(parents=True)
    path.write_text("my own instructions\n", encoding="utf-8")

    assert main(["install", "--dir", str(tmp_path), "--force"]) == 0

    assert path.read_text(encoding="utf-8") == CLI_SKILL


def test_install_json_reports_the_path_and_state(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["install", "--dir", str(tmp_path), "--json"]) == 0

    assert json.loads(capsys.readouterr().out) == {
        "agent": None,
        "path": str(tmp_path / SKILL_RELATIVE_PATH),
        "root": str(tmp_path),
        "state": "installed",
    }


def test_install_writes_to_a_named_agent_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A named agent resolves to its own skill root, which is all a name adds."""
    agent = CodingAgent(name="probe", label="Probe Harness", skill_root=tmp_path / "probe")
    monkeypatch.setattr(coding_agents, "CODING_AGENTS", (agent,))

    assert main(["install", "probe"]) == 0

    assert (agent.skill_root / SKILL_RELATIVE_PATH).is_file()


def test_install_lists_every_known_agent(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["install", "--list"]) == 0

    output = capsys.readouterr().out
    for agent in CODING_AGENTS:
        assert agent.name in output
        assert agent.label in output
        assert str(agent.skill_root) in output
    # Anything this table does not know is served by an explicit root.
    assert "--dir" in output


def test_install_names_the_agents_it_knows_for_an_unknown_one(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["install", "bogus"])

    assert exit_info.value.code == 2
    captured = capsys.readouterr()
    assert "unknown agent 'bogus'" in captured.err
    assert "claude" in captured.err and "codex" in captured.err


def test_install_requires_exactly_one_target(capsys: pytest.CaptureFixture[str]) -> None:
    for argv in (
        ["install"],
        ["install", "codex", "--dir", "/tmp/nowhere"],
        ["install", "--list", "codex"],
    ):
        with pytest.raises(SystemExit) as exit_info:
            main(argv)
        assert exit_info.value.code == 2
    assert "usage: zett install" in capsys.readouterr().err


def test_install_refuses_a_skill_root_that_is_a_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "not-a-directory"
    target.write_text("x", encoding="utf-8")

    assert main(["install", "--dir", str(target)]) == 1

    assert "is not a directory" in capsys.readouterr().err


def test_install_is_a_listed_user_command(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--help"]) == 0

    assert "install" in capsys.readouterr().out
