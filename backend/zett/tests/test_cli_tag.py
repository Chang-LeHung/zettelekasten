"""`zett tag` manages the taxonomy and assignments through the running server."""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

import pytest

from zett.cli import tag


class Recorder:
    """Stand in for the HTTP client: answer in order and remember every call."""

    def __init__(self, *answers: Any, error: Exception | None = None) -> None:
        self._answers = list(answers) or [None]
        self._error = error
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def __call__(self, method: str, path: str, payload: dict[str, Any] | None = None, **_: Any) -> Any:
        self.calls.append((method, path, payload))
        if self._error is not None:
            raise self._error
        return self._answers[min(len(self.calls), len(self._answers)) - 1]


def _tree() -> list[dict[str, Any]]:
    return [
        {
            "id": "tag-python",
            "path": "Engineering/Python",
            "direct_count": 1,
            "total_count": 2,
            "children": [
                {
                    "id": "tag-asyncio",
                    "path": "Engineering/Python/Asyncio",
                    "direct_count": 0,
                    "total_count": 0,
                    "children": [
                        {
                            "id": "tag-tasks",
                            "path": "Engineering/Python/Asyncio/Tasks",
                            "direct_count": 1,
                            "total_count": 1,
                            "children": [],
                        }
                    ],
                },
                {
                    "id": "tag-rust",
                    "path": "Engineering/Rust",
                    "direct_count": 0,
                    "total_count": 0,
                    "children": [],
                },
            ],
        },
        {"id": "tag-zett", "path": "Projects/Zett", "direct_count": 0, "total_count": 0, "children": []},
    ]


def _artifact(*paths: str) -> dict[str, Any]:
    return {
        "id": "artifact-1",
        "artifact_type": "card",
        "status": "saved",
        "tags": [
            {"id": f"tag-{path.lower().replace('/', '-')}", "path": path, "name": path.rsplit("/", 1)[-1]}
            for path in paths
        ],
    }


def test_list_prints_the_tree_with_counts_and_ids(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(tag, "request_json", Recorder(_tree()))

    exit_code = tag.main(["list"])

    lines = capsys.readouterr().out.splitlines()
    assert exit_code == 0
    assert lines[0] == "Engineering/Python  1/2  tag-python"
    assert lines[1] == "├── Engineering/Python/Asyncio  0/0  tag-asyncio"
    assert lines[2] == "│   └── Engineering/Python/Asyncio/Tasks  1/1  tag-tasks"
    assert lines[3] == "└── Engineering/Rust  0/0  tag-rust"
    assert lines[4] == "Projects/Zett  0/0  tag-zett"


@pytest.mark.parametrize("command", ["add", "remove", "set"])
def test_path_help_shows_what_a_tag_path_looks_like(
    command: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A shell user has to see the shape of a path, not only its name."""
    with pytest.raises(SystemExit) as exit_info:
        tag.main([command, "--help"])

    help_text = " ".join(capsys.readouterr().out.split())
    assert exit_info.value.code == 0
    assert "for example Engineering/Python" in help_text


def test_list_help_explains_the_direct_and_total_counts(capsys: pytest.CaptureFixture[str]) -> None:
    """`0/1` puzzled a reader once; the help has to say what the two numbers mean."""
    with pytest.raises(SystemExit) as exit_info:
        tag.main(["list", "--help"])

    help_text = " ".join(capsys.readouterr().out.split())
    assert exit_info.value.code == 0
    assert "direct counts the artifacts tagged exactly there" in help_text
    assert "0/1 when the only assignment sits on its child" in help_text


def test_create_prints_the_id_and_json_when_asked(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    recorder = Recorder({"id": "tag-zett", "path": "Projects/Zett"})
    monkeypatch.setattr(tag, "request_json", recorder)

    assert tag.main(["create", "Projects/Zett", "--description", "Zett work", "--color", "#3b82f6"]) == 0
    assert capsys.readouterr().out == "tag-zett\n"
    assert recorder.calls == [
        (
            "POST",
            "/api/library/tags",
            {"path": "Projects/Zett", "description": "Zett work", "color": "#3b82f6"},
        )
    ]


def test_update_sends_only_the_fields_it_was_given(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    recorder = Recorder({"id": "tag-asyncio", "path": "Engineering/Python/Async"})
    monkeypatch.setattr(tag, "request_json", recorder)

    exit_code = tag.main(["update", "tag-asyncio", "--path", "Engineering/Python/Async"])

    assert exit_code == 0
    assert capsys.readouterr().out == "tag-asyncio\n"
    assert recorder.calls[0] == ("PUT", "/api/library/tags/tag-asyncio", {"path": "Engineering/Python/Async"})


@pytest.mark.parametrize(
    "argv",
    [
        ["update", "tag-asyncio"],  # nothing to change
        ["add", "artifact-1"],  # argparse: at least one path
        ["set", "artifact-1"],  # either paths or --clear
        ["set", "artifact-1", "Projects/Zett", "--clear"],  # both at once
        # Values a tag row and a path listing cannot carry.
        ["create", "a//b"],
        ["create", "/leading"],
        ["create", "a\x07b"],
        ["get", "a b"],
        ["get", "x" * 65],
        ["update", "tag-asyncio", "--description", "x" * 1_001],
        ["add", "a b", "Projects/Zett"],
    ],
)
def test_usage_errors_exit_two_without_calling_the_server(
    argv: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(tag, "request_json", lambda *args, **kwargs: calls.append(args))

    with pytest.raises(SystemExit) as exit_info:
        tag.main(argv)

    assert exit_info.value.code == 2
    assert calls == []


def test_add_resolves_paths_to_ids_and_prints_the_resulting_tags(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    recorder = Recorder(_tree(), _artifact("Engineering/Python"), _artifact("Engineering/Python", "Projects/Zett"))
    monkeypatch.setattr(tag, "request_json", recorder)

    exit_code = tag.main(["add", "artifact-1", "Engineering/Python", "Projects/Zett"])

    assert exit_code == 0
    assert capsys.readouterr().out == "Engineering/Python\nProjects/Zett\n"
    assert recorder.calls[0] == ("GET", "/api/library/tags", None)
    assert recorder.calls[1] == ("PUT", "/api/library/tags/tag-python/artifacts/artifact-1", None)
    assert recorder.calls[2] == ("PUT", "/api/library/tags/tag-zett/artifacts/artifact-1", None)


def test_add_creates_a_path_the_taxonomy_lacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = Recorder(_tree(), {"id": "tag-new", "path": "Projects/New"}, _artifact("Projects/New"))
    monkeypatch.setattr(tag, "request_json", recorder)

    exit_code = tag.main(["add", "artifact-1", "Projects/New"])

    assert exit_code == 0
    assert recorder.calls == [
        ("GET", "/api/library/tags", None),
        ("POST", "/api/library/tags", {"path": "Projects/New"}),
        ("PUT", "/api/library/tags/tag-new/artifacts/artifact-1", None),
    ]


def test_remove_refuses_a_path_the_taxonomy_does_not_have(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Detaching must not invent a tag: only the path that exists can come off."""
    recorder = Recorder(_tree())
    monkeypatch.setattr(tag, "request_json", recorder)

    with pytest.raises(SystemExit) as exit_info:
        tag.main(["remove", "artifact-1", "Nope/Missing"])

    assert exit_info.value.code == 2
    assert "unknown tag path" in capsys.readouterr().err
    assert recorder.calls == [("GET", "/api/library/tags", None)]


def test_remove_detaches_every_named_path(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    recorder = Recorder(_tree(), _artifact("Engineering/Python"))
    monkeypatch.setattr(tag, "request_json", recorder)

    exit_code = tag.main(["remove", "artifact-1", "Projects/Zett"])

    assert exit_code == 0
    assert capsys.readouterr().out == "Engineering/Python\n"
    assert recorder.calls[1] == ("DELETE", "/api/library/tags/tag-zett/artifacts/artifact-1", None)


def test_set_replaces_the_whole_set_or_clears_it(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    recorder = Recorder(_artifact("Projects/Zett"), _artifact())
    monkeypatch.setattr(tag, "request_json", recorder)

    assert tag.main(["set", "artifact-1", "Projects/Zett"]) == 0
    assert capsys.readouterr().out == "Projects/Zett\n"
    assert recorder.calls[0] == ("PUT", "/api/library/tags/artifacts/artifact-1", {"paths": ["Projects/Zett"]})

    assert tag.main(["set", "artifact-1", "--clear"]) == 0
    assert capsys.readouterr().out == ""
    assert recorder.calls[1] == ("PUT", "/api/library/tags/artifacts/artifact-1", {"paths": []})


def test_delete_sends_the_destructive_flags_the_api_requires(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    recorder = Recorder({"ok": True})
    monkeypatch.setattr(tag, "request_json", recorder)

    exit_code = tag.main(["delete", "tag-python", "--recursive", "--force"])

    assert exit_code == 0
    assert capsys.readouterr().out == "deleted tag-python\n"
    assert recorder.calls[0] == ("DELETE", "/api/library/tags/tag-python?recursive=True&force=True", None)


def test_a_failing_request_exits_one_and_explains_itself(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from zett.cli.client import ServerRequestError

    monkeypatch.setattr(tag, "request_json", Recorder(error=ServerRequestError("409 Conflict: tag has children")))

    exit_code = tag.main(["delete", "tag-python"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "409 Conflict: tag has children" in captured.err


def test_importing_the_tag_command_imports_no_server_dependency() -> None:
    """The command must stay a client: importing it cannot pull in the app."""
    check = (
        "import sys, zett.cli.tag; "
        "heavy = [name for name in ('fastapi', 'sqlalchemy', 'uvicorn', 'httpx', 'zett_agent') if name in sys.modules]; "
        "print(heavy)"
    )
    result = subprocess.run([sys.executable, "-c", check], capture_output=True, text=True)

    assert result.returncode == 0
    assert result.stdout.strip() == "[]"


def test_get_prints_the_tag_as_json(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(tag, "request_json", Recorder({"id": "tag-zett", "path": "Projects/Zett"}))

    assert tag.main(["get", "tag-zett"]) == 0
    assert json.loads(capsys.readouterr().out)["path"] == "Projects/Zett"
