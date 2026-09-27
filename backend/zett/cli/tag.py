"""Create library tags and assign them to artifacts through the running server.

Tags are library-scoped, so every command here works without a conversation:
the taxonomy lives in the server's database, and this module only names the
endpoints that read and change it.
"""

from __future__ import annotations

import argparse
import json
import urllib.parse
from collections.abc import Iterator, Sequence
from typing import Any

from . import PROGRAM_NAME, validation
from .client import request_json
from .errors import UsageError, run

TAGS_PATH = "/api/library/tags"


def build_parser() -> argparse.ArgumentParser:
    """Build the parser for ``zett tag`` and its subcommands."""
    parser = argparse.ArgumentParser(
        prog=f"{PROGRAM_NAME} tag",
        description=(
            "Manage the library tag taxonomy and the tags an artifact carries. Tags are a "
            "recursive path tree; assigning one creates the path and every missing parent."
        ),
    )
    commands = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)

    listing = commands.add_parser(
        "list",
        help="Print the tag tree",
        description=(
            "Print the complete tag tree. Every line is `path  direct/total  id`, where direct counts the "
            "artifacts tagged exactly there and total counts those plus everything tagged in its "
            "descendants, so a parent node reads 0/1 when the only assignment sits on its child."
        ),
    )
    listing.add_argument("--json", action="store_true", help="Print the raw tree instead of one line per tag")
    listing.set_defaults(handler=_list)

    get = commands.add_parser("get", help="Print one tag", description="Print one tag as JSON.")
    get.add_argument("tag_id", help="Tag id, as `zett tag list` prints it")
    get.set_defaults(handler=_get)

    create = commands.add_parser(
        "create",
        help="Create a tag path",
        description="Create a tag path and any missing parent tag it names.",
    )
    create.add_argument("path", help="Display path separated by slashes, for example Engineering/Python")
    create.add_argument("--description", help="Optional description shown on the tag")
    create.add_argument("--color", help="Optional color shown on the tag")
    create.add_argument("--json", action="store_true", help="Print the stored tag instead of its id")
    create.set_defaults(handler=_create)

    update = commands.add_parser(
        "update",
        help="Rename, move, or restyle a tag",
        description="Rename, move, or restyle one leaf tag.",
    )
    update.add_argument("tag_id", help="Tag id, as `zett tag list` prints it")
    update.add_argument("--path", help="New display path; a tag with children cannot move")
    update.add_argument("--description", help="New description")
    update.add_argument("--color", help="New color")
    update.add_argument("--json", action="store_true", help="Print the stored tag instead of its id")
    update.set_defaults(handler=_update)

    delete = commands.add_parser("delete", help="Delete a tag", description="Delete one tag.")
    delete.add_argument("tag_id", help="Tag id, as `zett tag list` prints it")
    delete.add_argument("--recursive", action="store_true", help="Also delete its child tags")
    delete.add_argument("--force", action="store_true", help="Remove the artifact assignments that use it")
    delete.set_defaults(handler=_delete)

    add = commands.add_parser(
        "add",
        help="Attach tags to an artifact or static asset",
        description=(
            "Attach tags to one library resource — an artifact, or a static asset with --asset — "
            "keeping the tags it already carries. Both kinds share one taxonomy."
        ),
    )
    add.add_argument(
        "resource_id",
        metavar="ID",
        help="Artifact id, or a static asset id when --asset is set",
    )
    add.add_argument(
        "paths",
        nargs="+",
        metavar="TAG_PATH",
        help="Tag paths to attach, for example Engineering/Python or Projects/Zett; a path the taxonomy "
        "does not have yet is created",
    )
    _add_resource_kind(add)
    add.add_argument("--json", action="store_true", help="Print the resource instead of its tag paths")
    add.set_defaults(handler=_add)

    remove = commands.add_parser(
        "remove",
        help="Detach tags from an artifact or static asset",
        description=(
            "Detach tags from one library resource — an artifact, or a static asset with --asset — "
            "keeping the tags it still carries."
        ),
    )
    remove.add_argument(
        "resource_id",
        metavar="ID",
        help="Artifact id, or a static asset id when --asset is set",
    )
    remove.add_argument(
        "paths",
        nargs="+",
        metavar="TAG_PATH",
        help="Tag paths to detach, for example Engineering/Python; the path has to exist already",
    )
    _add_resource_kind(remove)
    remove.add_argument("--json", action="store_true", help="Print the resource instead of its tag paths")
    remove.set_defaults(handler=_remove)

    replace = commands.add_parser(
        "set",
        help="Replace the tag set of an artifact or static asset",
        description=(
            "Replace every tag one library resource carries — an artifact, or a static asset with "
            "--asset — with the paths given here."
        ),
    )
    replace.add_argument(
        "resource_id",
        metavar="ID",
        help="Artifact id, or a static asset id when --asset is set",
    )
    replace.add_argument(
        "paths",
        nargs="*",
        metavar="TAG_PATH",
        help="The complete tag set, for example Engineering/Python Projects/Zett; a path the taxonomy "
        "does not have yet is created",
    )
    _add_resource_kind(replace)
    replace.add_argument("--clear", action="store_true", help="Assign no tags at all")
    replace.add_argument("--json", action="store_true", help="Print the resource instead of its tag paths")
    replace.set_defaults(handler=_set)
    return parser


def _add_resource_kind(parser: argparse.ArgumentParser) -> None:
    """Let one command classify either kind of library resource.

    Artifacts and static assets share the taxonomy, so the only thing a caller
    has to state is which kind the id names: the endpoint differs, the meaning of
    a tag does not.
    """
    parser.add_argument(
        "--asset",
        action="store_true",
        help="Treat ID as a static asset id instead of an artifact id",
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run one tag subcommand and return its exit status."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(parser, args.handler, args)


def _list(args: argparse.Namespace) -> int:
    """Print the tag tree with the counts the library view shows."""
    tree = request_json("GET", TAGS_PATH)
    if args.json:
        print(json.dumps(tree, indent=2, ensure_ascii=False))
        return 0
    for line in _tree_lines(tree):
        print(line)
    return 0


def _tree_lines(nodes: list[dict[str, Any]], prefix: str = "", *, root: bool = True) -> Iterator[str]:
    """Yield one line per tag, drawing the hierarchy the way ``tree`` does.

    A path names a tag in every other command, so each line keeps the full path
    next to the counts and the id; the connectors carry the structure instead of
    a run of spaces that is easy to misread once a branch has siblings.
    """
    last_index = len(nodes) - 1
    for index, node in enumerate(nodes):
        is_last = index == last_index
        if root:
            yield _tag_line(node)
        else:
            connector = "└── " if is_last else "├── "
            yield f"{prefix}{connector}{_tag_line(node)}"
        children = node.get("children") or []
        if not children:
            continue
        child_prefix = "" if root else prefix + ("    " if is_last else "│   ")
        yield from _tree_lines(children, child_prefix, root=False)


def _tag_line(node: dict[str, Any]) -> str:
    """Render one tag as path, direct/total counts, and id."""
    return f"{node['path']}  {node['direct_count']}/{node['total_count']}  {node['id']}"


def _get(args: argparse.Namespace) -> int:
    """Print one tag as JSON."""
    tag_id = validation.identifier(args.tag_id, field="tag id")
    print(json.dumps(request_json("GET", f"{TAGS_PATH}/{urllib.parse.quote(tag_id)}"), indent=2, ensure_ascii=False))
    return 0


def _create(args: argparse.Namespace) -> int:
    """Create a tag path and print its id, or the stored tag with ``--json``."""
    payload: dict[str, Any] = {"path": validation.tag_path(args.path)}
    if args.description is not None:
        payload["description"] = validation.text(
            args.description,
            field="--description",
            max_length=validation.MAX_DESCRIPTION_CHARS,
        )
    if args.color is not None:
        payload["color"] = validation.text(args.color, field="--color", max_length=validation.MAX_COLOR_CHARS)
    return _print_tag(request_json("POST", TAGS_PATH, payload), as_json=args.json)


def _update(args: argparse.Namespace) -> int:
    """Rename, move, or restyle one tag."""
    tag_id = validation.identifier(args.tag_id, field="tag id")
    payload: dict[str, Any] = {}
    if args.path is not None:
        payload["path"] = validation.tag_path(args.path)
    if args.description is not None:
        payload["description"] = validation.text(
            args.description,
            field="--description",
            max_length=validation.MAX_DESCRIPTION_CHARS,
        )
    if args.color is not None:
        payload["color"] = validation.text(args.color, field="--color", max_length=validation.MAX_COLOR_CHARS)
    if not payload:
        raise UsageError("--path, --description, or --color is required")
    updated = request_json("PUT", f"{TAGS_PATH}/{urllib.parse.quote(tag_id)}", payload)
    return _print_tag(updated, as_json=args.json)


def _delete(args: argparse.Namespace) -> int:
    """Delete one tag, requiring the explicit flags the API asks for."""
    tag_id = validation.identifier(args.tag_id, field="tag id")
    query = urllib.parse.urlencode({"recursive": args.recursive, "force": args.force})
    request_json("DELETE", f"{TAGS_PATH}/{urllib.parse.quote(tag_id)}?{query}")
    print(f"deleted {tag_id}")
    return 0


def _add(args: argparse.Namespace) -> int:
    """Attach every named path to one resource, one assignment at a time.

    A path the taxonomy does not have yet is created first, because assigning a
    tag the server has never seen is how a shell names a new one.
    """
    kind, resource_id = _tagged_resource(args)
    paths = [validation.tag_path(path) for path in args.paths]
    known = {node["path"]: node["id"] for _, node in _walk(request_json("GET", TAGS_PATH))}
    tagged: dict[str, Any] | None = None
    for path in paths:
        tag_id = known.get(path) or request_json("POST", TAGS_PATH, {"path": path})["id"]
        tagged = request_json("PUT", f"{TAGS_PATH}/{tag_id}/{kind}/{resource_id}")
    assert tagged is not None  # `paths` is a required argument
    return _print_tagged_resource(tagged, as_json=args.json)


def _remove(args: argparse.Namespace) -> int:
    """Detach every named path from one resource, one assignment at a time."""
    kind, resource_id = _tagged_resource(args)
    tagged: dict[str, Any] | None = None
    for tag_id in _tag_ids([validation.tag_path(path) for path in args.paths]).values():
        tagged = request_json("DELETE", f"{TAGS_PATH}/{tag_id}/{kind}/{resource_id}")
    assert tagged is not None  # `paths` is a required argument
    return _print_tagged_resource(tagged, as_json=args.json)


def _set(args: argparse.Namespace) -> int:
    """Replace the complete tag set of one resource."""
    if args.clear and args.paths:
        raise UsageError("--clear assigns no tags, so it cannot be combined with tag paths")
    if not args.clear and not args.paths:
        raise UsageError("name at least one TAG_PATH, or pass --clear to remove every tag")
    kind, resource_id = _tagged_resource(args)
    tagged = request_json(
        "PUT",
        f"{TAGS_PATH}/{kind}/{resource_id}",
        {"paths": [] if args.clear else [validation.tag_path(item) for item in args.paths]},
    )
    return _print_tagged_resource(tagged, as_json=args.json)


def _tagged_resource(args: argparse.Namespace) -> tuple[str, str]:
    """Return the endpoint segment and quoted id this command's id names."""
    field = "static asset id" if args.asset else "artifact id"
    resource_id = urllib.parse.quote(validation.identifier(args.resource_id, field=field))
    return ("assets" if args.asset else "artifacts", resource_id)


def _tag_ids(paths: Sequence[str]) -> dict[str, str]:
    """Map the tag paths a shell names to the tag ids the endpoints take."""
    by_path = {node["path"]: node["id"] for _, node in _walk(request_json("GET", TAGS_PATH))}
    unknown = [path for path in paths if path not in by_path]
    if unknown:
        raise UsageError(f"unknown tag path(s): {', '.join(unknown)}; create them with `zett tag create`")
    return {path: by_path[path] for path in paths}


def _walk(nodes: list[dict[str, Any]], depth: int = 0) -> Iterator[tuple[int, dict[str, Any]]]:
    """Yield every node of a tag tree with its depth."""
    for node in nodes:
        yield depth, node
        yield from _walk(node.get("children") or [], depth + 1)


def _print_tag(tag: dict[str, Any], *, as_json: bool) -> int:
    """Print one tag as its id, or as the stored entity."""
    print(json.dumps(tag, indent=2, ensure_ascii=False) if as_json else tag["id"])
    return 0


def _print_tagged_resource(resource: dict[str, Any], *, as_json: bool) -> int:
    """Print one artifact or static asset as its tag paths, or as the stored entity."""
    if as_json:
        print(json.dumps(resource, indent=2, ensure_ascii=False))
        return 0
    for tag in sorted(resource["tags"], key=lambda item: item["path"]):
        print(tag["path"])
    return 0
