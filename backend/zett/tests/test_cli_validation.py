"""The command line refuses anything that could pollute stored data."""

from __future__ import annotations

from pathlib import Path

import pytest

from zett.cli import validation
from zett.cli.errors import UsageError


def test_text_trims_and_refuses_blank_oversized_or_control_values() -> None:
    assert validation.text("  Idea  ", field="--title", max_length=10) == "Idea"

    with pytest.raises(UsageError, match="cannot be blank"):
        validation.text("   ", field="--title", max_length=10)
    with pytest.raises(UsageError, match="longer than 10"):
        validation.text("x" * 11, field="--title", max_length=10)
    with pytest.raises(UsageError, match="control characters"):
        validation.text("bad\x00title", field="--title", max_length=10)
    with pytest.raises(UsageError, match="control characters"):
        validation.text("two\nlines", field="--title", max_length=10)


def test_bodies_keep_newlines_and_tabs_but_no_other_control_characters() -> None:
    assert validation.text("a\nb\tc", field="--body", max_length=100, allow_newlines=True) == "a\nb\tc"

    with pytest.raises(UsageError, match="control characters"):
        validation.text("a\x00b", field="--body", max_length=100, allow_newlines=True)
    with pytest.raises(UsageError, match="control characters"):
        validation.text("a\x1bb", field="--body", max_length=100, allow_newlines=True)


def test_tag_path_normalizes_and_refuses_empty_or_oversized_segments() -> None:
    assert validation.tag_path(" Engineering / Python ") == "Engineering/Python"

    for value, message in (
        ("   ", "cannot be blank"),
        ("/leading", "empty segment"),
        ("trailing/", "empty segment"),
        ("a//b", "empty segment"),
        ("a\x07b", "control characters"),
    ):
        with pytest.raises(UsageError, match=message):
            validation.tag_path(value)
    with pytest.raises(UsageError, match="longer than 100"):
        validation.tag_path("x" * 101)


def test_identifier_refuses_whitespace_separators_and_oversized_ids() -> None:
    assert validation.identifier(" artifact-1 ", field="artifact id") == "artifact-1"

    for value, message in (
        ("", "cannot be blank"),
        ("a b", "whitespace"),
        ("a/b", "whitespace"),
        ("a\x00b", "control characters"),
    ):
        with pytest.raises(UsageError, match=message):
            validation.identifier(value, field="artifact id")
    with pytest.raises(UsageError, match="longer than 64"):
        validation.identifier("x" * 65, field="artifact id")


def test_metadata_is_a_plain_token_mapping_with_exactly_one_source() -> None:
    assert validation.metadata(["origin=cli", "team=zett"], " cron ") == {
        "origin": "cli",
        "team": "zett",
        "source": "cron",
    }

    for pairs, source, message in (
        ([], "   ", "cannot be blank"),
        (["source=x"], "cli", "set by --source"),
        (["origin=a", "origin=b"], "cli", "given twice"),
        (["bad key=x"], "cli", "plain token"),
        (["broken"], "cli", "KEY=VALUE"),
        (["origin=" + "x" * 1_001], "cli", "longer than 1000"),
        ([f"key{index}=v" for index in range(3_000)], "cli", "longer than 20000"),
    ):
        with pytest.raises(UsageError, match=message):
            validation.metadata(pairs, source)


def test_read_text_is_bounded_and_reports_unreadable_sources(tmp_path: Path) -> None:
    body = tmp_path / "body.md"
    body.write_text("x" * 20, encoding="utf-8")
    binary = tmp_path / "binary.md"
    binary.write_bytes(b"\xff\xfe\x00")

    assert validation.read_text(str(body), field="--body-file", max_length=20, allow_newlines=True) == "x" * 20
    with pytest.raises(UsageError, match="longer than 19"):
        validation.read_text(str(body), field="--body-file", max_length=19, allow_newlines=True)
    with pytest.raises(UsageError, match="could not read"):
        validation.read_text(str(tmp_path / "missing.md"), field="--body-file", max_length=10)
    with pytest.raises(UsageError, match="could not read"):
        validation.read_text(str(binary), field="--body-file", max_length=10, allow_newlines=True)
    with pytest.raises(UsageError, match="needs a file path"):
        validation.read_text(None, field="--body-file", max_length=10)


def test_json_object_refuses_unknown_keys_and_non_objects() -> None:
    allowed = frozenset({"title", "content"})

    assert validation.json_object('{"title": "x"}', field="content", allowed=allowed) == {"title": "x"}
    with pytest.raises(UsageError, match="unknown keys: evil"):
        validation.json_object('{"title": "x", "evil": 1}', field="content", allowed=allowed)
    with pytest.raises(UsageError, match="must be a JSON object"):
        validation.json_object("[1]", field="content", allowed=allowed)
    with pytest.raises(UsageError, match="not valid JSON"):
        validation.json_object("{", field="content", allowed=allowed)
