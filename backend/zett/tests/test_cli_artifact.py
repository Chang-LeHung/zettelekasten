"""`zett artifact` talks to the running server instead of opening the app."""

from __future__ import annotations

import io
import json
import subprocess
import sys
from typing import Any

import pytest

from zett.cli import artifact
from zett.cli.client import ServerRequestError


class Recorder:
    """Stand in for the HTTP client and remember what the command sent."""

    def __init__(self, answer: Any = None, *, error: Exception | None = None) -> None:
        self.answer = answer
        self.error = error
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def __call__(self, method: str, path: str, payload: dict[str, Any] | None = None, **_: Any) -> Any:
        self.calls.append((method, path, payload))
        if self.error is not None:
            raise self.error
        return self.answer


def _card(artifact_id: str = "artifact-1") -> dict[str, Any]:
    return {
        "id": artifact_id,
        "session_id": "session-1",
        "artifact_type": "card",
        "status": "saved",
        "content": {"artifact_type": "card", "title": "Piped", "content": "body"},
        "draft_content": None,
    }


def test_create_posts_a_card_built_from_flags(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = Recorder(_card())
    monkeypatch.setattr(artifact, "request_json", recorder)

    exit_code = artifact.main(
        ["create", "--type", "card", "--title", "Piped", "--body", "body", "--source", " cli "],
    )

    assert exit_code == 0
    assert capsys.readouterr().out == "artifact-1\n"
    method, path, payload = recorder.calls[0]
    assert (method, path) == ("POST", "/api/artifacts")
    assert payload == {
        "content": {"artifact_type": "card", "title": "Piped", "content": "body"},
        "status": "saved",
        # `--source` names who creates the artifact, and a blank one is refused.
        "metadata": {"source": "cli"},
    }


def test_create_reads_the_body_from_standard_input(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    recorder = Recorder(_card())
    monkeypatch.setattr(artifact, "request_json", recorder)
    monkeypatch.setattr(sys, "stdin", io.StringIO("from a pipe\n"))

    exit_code = artifact.main(
        ["create", "--type", "article", "--title", "Post", "--body-file", "-", "--source", "script:notes"],
    )

    assert exit_code == 0
    del capsys
    assert recorder.calls[0][2]["content"]["content"] == "from a pipe\n"


def test_create_accepts_json_content_for_a_supported_kind(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    recorder = Recorder(_card())
    monkeypatch.setattr(artifact, "request_json", recorder)
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"title": "Idea", "content": "Body", "card_type": "note"}'))

    exit_code = artifact.main(
        [
            "create",
            "--type",
            "card",
            "--content-file",
            "-",
            "--metadata",
            "origin=cli",
            "--source",
            "cli",
            "--json",
        ],
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["id"] == "artifact-1"
    payload = recorder.calls[0][2]
    assert payload["content"] == {
        "title": "Idea",
        "content": "Body",
        "card_type": "note",
        "artifact_type": "card",
    }
    assert payload["metadata"] == {"origin": "cli", "source": "cli"}


@pytest.mark.parametrize(
    "argv",
    [
        ["create", "--type", "card", "--body", "body"],  # missing --title
        ["create", "--type", "card", "--title", "T"],  # missing --body
        # `--source` is required, never blank, and never repeated through --metadata.
        ["create", "--type", "card", "--title", "T", "--body", "b"],
        ["create", "--type", "card", "--title", "T", "--body", "b", "--source", "   "],
        ["create", "--type", "card", "--title", "T", "--body", "b", "--source", "cli", "--metadata", "source=cron"],
        ["create", "--type", "card", "--title", "T", "--body", "b", "--source", "cli", "--metadata", "broken"],
        [
            "create",
            "--type",
            "card",
            "--title",
            "T",
            "--body",
            "b",
            "--source",
            "cli",
            "--metadata",
            "a=1",
            "--metadata",
            "a=2",
        ],
        # Values a shell could inject that storage and a listing cannot carry.
        ["create", "--type", "card", "--title", "two\nlines", "--body", "b", "--source", "cli"],
        ["create", "--type", "card", "--title", "T", "--body", "b", "--source", "bad\x00source"],
        ["create", "--type", "card", "--content", '{"title": "T", "content": "b", "evil": 1}', "--source", "cli"],
        ["create", "--type", "card", "--content", '{"title": "T", "content": 7}', "--source", "cli"],
        ["list", "--limit", "0"],
        ["list", "--limit", "501"],
        ["create", "--type", "card", "--title", "T", "--content", "not json", "--source", "cli"],
        ["delete", "a b"],
        # Images and LaTeX artifacts wait for their own interface.
        ["create", "--type", "image", "--title", "T", "--body", "b", "--source", "cli"],
        ["create", "--type", "latex_pdf", "--title", "T", "--body", "b", "--source", "cli"],
        ["create", "--type", "unknown", "--title", "T", "--body", "b", "--source", "cli"],
    ],
)
def test_create_rejects_flags_that_cannot_describe_an_artifact(
    argv: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(artifact, "request_json", lambda *args, **kwargs: calls.append(args))

    with pytest.raises(SystemExit) as exit_info:
        artifact.main(argv)

    assert exit_info.value.code == 2
    assert calls == []


def test_get_prints_the_artifact_it_asked_for(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    recorder = Recorder(_card("artifact-1?x"))
    monkeypatch.setattr(artifact, "request_json", recorder)

    exit_code = artifact.main(["get", "artifact-1?x"])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["id"] == "artifact-1?x"
    # A query character in an id must never escape into the request line.
    assert recorder.calls[0][:2] == ("GET", "/api/artifacts/artifact-1%3Fx")


def test_delete_sends_the_delete_and_prints_the_id(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    recorder = Recorder({"ok": True})
    monkeypatch.setattr(artifact, "request_json", recorder)

    exit_code = artifact.main(["delete", "artifact-1"])

    assert exit_code == 0
    assert capsys.readouterr().out == "deleted artifact-1\n"
    assert recorder.calls == [("DELETE", "/api/artifacts/artifact-1", None)]


def test_delete_surfaces_the_refusal_for_a_conversation_artifact(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from zett.cli.client import ServerRequestError

    monkeypatch.setattr(
        artifact,
        "request_json",
        Recorder(error=ServerRequestError("403 Forbidden: Artifact belongs to a conversation")),
    )

    exit_code = artifact.main(["delete", "artifact-1"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "belongs to a conversation" in captured.err


def test_delete_help_says_it_only_deletes_library_artifacts(capsys: pytest.CaptureFixture[str]) -> None:
    """The rule belongs in the help, not only in the server's answer."""
    with pytest.raises(SystemExit) as exit_info:
        artifact.main(["delete", "--help"])

    help_text = " ".join(capsys.readouterr().out.split())
    assert exit_info.value.code == 0
    assert "Only a library artifact" in help_text
    assert "delete that one in its conversation instead" in help_text
    assert "`zett artifact list` lists exactly the artifacts this command accepts" in help_text


def test_list_prints_one_line_per_artifact(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    recorder = Recorder([_card(), {**_card("artifact-2"), "artifact_type": "article", "status": "draft"}])
    monkeypatch.setattr(artifact, "request_json", recorder)

    exit_code = artifact.main(["list", "--query", "piped", "--limit", "5"])

    assert exit_code == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("artifact-1  card       saved  Piped")
    assert lines[1].startswith("artifact-2  article    draft  Piped")
    assert recorder.calls[0][1] == "/api/artifacts?q=piped&limit=5"


def test_a_failing_request_exits_one_and_explains_itself(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(artifact, "request_json", Recorder(error=ServerRequestError("422 Unprocessable: bad content")))

    exit_code = artifact.main(["create", "--type", "card", "--title", "T", "--body", "b", "--source", "cli"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "422 Unprocessable: bad content" in captured.err
    assert captured.out == ""


def test_importing_the_artifact_command_imports_no_server_dependency() -> None:
    """The command must stay a client: importing it cannot pull in the app."""
    check = (
        "import sys, zett.cli.artifact; "
        "heavy = [name for name in ('fastapi', 'sqlalchemy', 'uvicorn', 'httpx', 'zett_agent') if name in sys.modules]; "
        "print(heavy)"
    )
    result = subprocess.run([sys.executable, "-c", check], capture_output=True, text=True)

    assert result.returncode == 0
    assert result.stdout.strip() == "[]"
