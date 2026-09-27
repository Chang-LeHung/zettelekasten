"""Create and read library artifacts through the running server.

The command talks HTTP instead of opening the databases: the server already
owns the artifact tables, the file layout, and the tag sync, and a client that
did the same work locally would import the whole application to do it.
"""

from __future__ import annotations

import argparse
import json
import urllib.parse
from collections.abc import Sequence
from typing import Any

from . import PROGRAM_NAME, validation
from .arguments import bounded_int
from .client import request_json
from .errors import UsageError, run

#: Kinds the command line creates today. An image artifact needs an asset to
#: point at and a LaTeX artifact needs a server-managed project directory, so
#: both wait for their own interface rather than pretending a shell could
#: describe them with a title and a body.
ARTIFACT_TYPES = ("card", "article", "slides")
STATUSES = ("draft", "saved")
#: Longest typed-content document the JSON flags accept, before it is parsed.
MAX_CONTENT_JSON_CHARS = 1_000_000
#: Keys each artifact kind's stored content model accepts. Pydantic ignores an
#: unknown field, so a typo would silently store less than the caller wrote;
#: naming the allowed keys turns that into a usage error.
CONTENT_KEYS = {
    "card": frozenset({"artifact_type", "title", "summary", "content", "card_type", "keywords", "suggested_tags"}),
    "article": frozenset({"artifact_type", "title", "summary", "content", "subtitle", "keywords", "suggested_tags"}),
    "slides": frozenset({"artifact_type", "title", "summary", "content", "subtitle", "keywords", "suggested_tags"}),
}


def build_parser() -> argparse.ArgumentParser:
    """Build the parser for ``zett artifact`` and its subcommands."""
    parser = argparse.ArgumentParser(
        prog=f"{PROGRAM_NAME} artifact",
        description=(
            "Create, read, delete, and list library artifacts: artifacts that belong to no conversation. "
            "The server stores them under its hidden library session, so they appear in the library view "
            "like any other artifact and never as a chat."
        ),
    )
    commands = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)

    create = commands.add_parser("create", help="Create one artifact", description="Create one artifact.")
    create.add_argument("--type", dest="artifact_type", choices=ARTIFACT_TYPES, required=True, help="Artifact kind")
    create.add_argument("--title", help="Artifact title")
    create.add_argument("--body", help="Markdown body, or - to read it from standard input")
    create.add_argument("--body-file", help="Read the Markdown body from a file, or - for standard input")
    create.add_argument("--summary", help="Card summary")
    create.add_argument("--subtitle", help="Article or slide-deck subtitle")
    create.add_argument("--content", help="Typed content as JSON, when a flag cannot name a field")
    create.add_argument("--content-file", help="Read the content JSON from a file, or - for standard input")
    create.add_argument("--raw-content", help="Source text the artifact was created from")
    create.add_argument(
        "--status",
        choices=STATUSES,
        default="saved",
        help="Saved artifacts appear in the library (default: %(default)s)",
    )
    create.add_argument(
        "--source",
        required=True,
        help=(
            "Who creates this artifact, e.g. cli or cron:nightly-import. Stored as metadata.source, "
            "which the server refuses to leave blank: an artifact with no conversation has nothing "
            "else to attribute it to"
        ),
    )
    create.add_argument(
        "--metadata",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Repeatable extra metadata; source is set by --source and cannot be repeated here",
    )
    create.add_argument("--json", action="store_true", help="Print the stored artifact instead of its id")
    create.set_defaults(handler=_create)

    get = commands.add_parser("get", help="Print one artifact", description="Print one artifact as JSON.")
    get.add_argument(
        "artifact_id", help="Artifact id, as `zett artifact create` prints it or `zett artifact list` lists it"
    )
    get.set_defaults(handler=_get)

    delete = commands.add_parser(
        "delete",
        help="Delete one artifact from the library",
        description=(
            "Delete one artifact from the library. Only a library artifact — one that belongs to no "
            "conversation — can be deleted here: an artifact that belongs to a conversation is refused "
            "(403) and left untouched, so delete that one in its conversation instead. "
            "`zett artifact list` lists exactly the artifacts this command accepts."
        ),
    )
    delete.add_argument("artifact_id", help="Artifact id, as `zett artifact create` prints it")
    delete.set_defaults(handler=_delete)

    listing = commands.add_parser("list", help="List artifacts", description="List artifacts in the library.")
    listing.add_argument("--query", "-q", help="Search titles, summaries, and content")
    listing.add_argument(
        "--limit", type=bounded_int(1, 500), default=20, help="How many to print (default: %(default)s)"
    )
    listing.set_defaults(handler=_list)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one artifact subcommand and return its exit status."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(parser, args.handler, args)


def _create(args: argparse.Namespace) -> int:
    """Post one artifact and print its id, or the stored artifact with ``--json``."""
    payload: dict[str, Any] = {
        "content": {"artifact_type": args.artifact_type, **_content(args)},
        "status": args.status,
        "metadata": validation.metadata(args.metadata, args.source),
    }
    if args.raw_content is not None:
        payload["raw_content"] = validation.text(
            args.raw_content,
            field="--raw-content",
            max_length=validation.MAX_BODY_CHARS,
            allow_newlines=True,
        )
    created = request_json("POST", "/api/artifacts", payload)
    if args.json:
        print(json.dumps(created, indent=2, ensure_ascii=False))
    else:
        print(created["id"])
    return 0


def _get(args: argparse.Namespace) -> int:
    """Print one artifact as JSON."""
    artifact_id = validation.identifier(args.artifact_id, field="artifact id")
    artifact = request_json("GET", f"/api/artifacts/{urllib.parse.quote(artifact_id)}")
    print(json.dumps(artifact, indent=2, ensure_ascii=False))
    return 0


def _delete(args: argparse.Namespace) -> int:
    """Delete one library artifact; the server refuses one a conversation owns."""
    artifact_id = validation.identifier(args.artifact_id, field="artifact id")
    request_json("DELETE", f"/api/artifacts/{urllib.parse.quote(artifact_id)}")
    print(f"deleted {artifact_id}")
    return 0


def _list(args: argparse.Namespace) -> int:
    """Print one line per artifact, newest first."""
    search = validation.query(args.query)
    query = urllib.parse.urlencode({"q": search, "limit": args.limit}) if search else f"limit={args.limit}"
    artifacts = request_json("GET", f"/api/artifacts?{query}")
    for artifact in artifacts:
        content = artifact.get("content") or artifact.get("draft_content") or {}
        title = content.get("title") or "(untitled)"
        print(f"{artifact['id']}  {artifact['artifact_type']:<10} {artifact['status']:<6} {title}")
    return 0


def _content(args: argparse.Namespace) -> dict[str, Any]:
    """Build the typed content from raw JSON or from the text flags."""
    if args.content is not None or args.content_file is not None:
        return _json_content(args)
    content: dict[str, Any] = {
        "title": validation.text(args.title or "", field="--title", max_length=validation.MAX_TITLE_CHARS),
        "content": _body(args, max_length=validation.MAX_BODY_CHARS),
    }
    if args.artifact_type == "card" and args.summary is not None:
        content["summary"] = validation.text(
            args.summary,
            field="--summary",
            max_length=validation.MAX_SUMMARY_CHARS,
        )
    if args.artifact_type in {"article", "slides"} and args.subtitle is not None:
        content["subtitle"] = validation.text(
            args.subtitle,
            field="--subtitle",
            max_length=validation.MAX_SUBTITLE_CHARS,
        )
    return content


def _json_content(args: argparse.Namespace) -> dict[str, Any]:
    """Return the typed content a JSON string or file carries, checked field by field."""
    if args.content is not None and args.content_file is not None:
        raise UsageError("--content and --content-file cannot be combined")
    if args.content_file is not None:
        document = validation.read_text(
            args.content_file,
            field="--content-file",
            max_length=MAX_CONTENT_JSON_CHARS,
            allow_newlines=True,
        )
    else:
        document = validation.text(
            args.content or "",
            field="--content",
            max_length=MAX_CONTENT_JSON_CHARS,
            allow_newlines=True,
        )
    payload = validation.json_object(document, field="content", allowed=CONTENT_KEYS[args.artifact_type])
    return _checked_content(args.artifact_type, payload)


def _checked_content(artifact_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate the fields the JSON document carries and drop the discriminator.

    Values are checked with the same limits the stored models use, so a payload
    cannot reach the database with a control character, an oversized body, or a
    keyword list the server would have to reject anyway.
    """
    content = {key: value for key, value in payload.items() if key != "artifact_type"}
    content["title"] = _string_field(content, "title", max_length=validation.MAX_TITLE_CHARS, required=True)
    content["content"] = _string_field(
        content,
        "content",
        max_length=validation.MAX_BODY_CHARS,
        required=True,
        allow_newlines=True,
    )
    if "summary" in content:
        content["summary"] = _string_field(content, "summary", max_length=validation.MAX_SUMMARY_CHARS)
    if "subtitle" in content:
        content["subtitle"] = _string_field(content, "subtitle", max_length=validation.MAX_SUBTITLE_CHARS)
    if "card_type" in content:
        content["card_type"] = _string_field(content, "card_type", max_length=100)
    if "keywords" in content:
        content["keywords"] = _keywords(content["keywords"])
    return content


def _string_field(
    payload: dict[str, Any],
    key: str,
    *,
    max_length: int,
    required: bool = False,
    allow_newlines: bool = False,
) -> str:
    """Return one text field of a JSON content document."""
    value = payload.get(key)
    if value is None:
        if required:
            raise UsageError(f"content.{key} is required")
        return ""
    if not isinstance(value, str):
        raise UsageError(f"content.{key} must be a string")
    return validation.text(value, field=f"content.{key}", max_length=max_length, allow_newlines=allow_newlines)


def _keywords(value: Any) -> list[str]:
    """Return a checked keyword list: strings, bounded in count and in length."""
    if not isinstance(value, list) or len(value) > 100:
        raise UsageError("content.keywords must be a list of at most 100 strings")
    return [
        validation.text(
            keyword if isinstance(keyword, str) else "",
            field="content.keywords[]",
            max_length=100,
        )
        for keyword in value
    ]


def _body(args: argparse.Namespace, *, max_length: int) -> str:
    """Return the body text from ``--body`` or ``--body-file``."""
    if args.body is None and args.body_file is None:
        raise UsageError("--body or --body-file is required when --content is not used")
    if args.body is not None and args.body_file is not None:
        raise UsageError("--body and --body-file cannot be combined")
    if args.body_file is not None:
        return validation.read_text(
            args.body_file,
            field="--body-file",
            max_length=max_length,
            allow_newlines=True,
        )
    if args.body == "-":
        return validation.read_text("-", field="--body", max_length=max_length, allow_newlines=True)
    return validation.text(args.body, field="--body", max_length=max_length, allow_newlines=True)
