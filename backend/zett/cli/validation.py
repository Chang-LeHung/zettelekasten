"""Validate every command-line value before it reaches the server.

The CLI is a client and must stay one: it cannot import the application's
schemas to reuse their models, so these checks mirror the limits those models
enforce and stop a bad value at the boundary instead of letting the server
answer with a traceback-shaped 422. What they add beyond "the server will
reject it" is what a shell can inject that a database row, a log line, and a
plain-text listing cannot carry: control characters, oversized payloads, and
ambiguous identifiers.
"""

from __future__ import annotations

import json
import sys
import unicodedata
from collections.abc import Iterable
from typing import Any

from .errors import UsageError

#: Longest Markdown body a card, article, or slide deck may carry.
MAX_BODY_CHARS = 1_000_000
#: Longest artifact or tag title (mirrors ``NonBlankName500``).
MAX_TITLE_CHARS = 500
#: Longest card summary, article or slide subtitle, and tag description.
MAX_SUMMARY_CHARS = 20_000
MAX_SUBTITLE_CHARS = 500
MAX_DESCRIPTION_CHARS = 1_000
#: Longest color string and metadata key.
MAX_COLOR_CHARS = 32
MAX_METADATA_KEY_CHARS = 64
#: Longest metadata value and the whole metadata mapping once serialized.
MAX_METADATA_VALUE_CHARS = 1_000
MAX_METADATA_TOTAL_CHARS = 20_000
#: Longest tag path, one of its segments, and one identifier.
MAX_TAG_PATH_CHARS = 500
MAX_TAG_SEGMENT_CHARS = 100
MAX_IDENTIFIER_CHARS = 64
#: Longest library search query.
MAX_QUERY_CHARS = 200

_LINE_FIELDS_ALLOWED = frozenset()
_BODY_FIELDS_ALLOWED = frozenset({"\n", "\t", "\r"})


def text(value: str, *, field: str, max_length: int, allow_newlines: bool = False) -> str:
    """Return one trimmed field, refusing a blank, oversized, or control character value.

    Bodies keep tabs and newlines, which are the Markdown they are made of; a
    single-line field keeps none of them, because a newline in a title would
    forge an extra line in `zett artifact list` and in every log record that
    previews it.
    """
    cleaned = value if allow_newlines else value.strip()
    if not cleaned.strip():
        raise UsageError(f"{field} cannot be blank")
    if len(cleaned) > max_length:
        raise UsageError(f"{field} is longer than {max_length} characters")
    _reject_control(cleaned, field=field, allow_newlines=allow_newlines)
    return cleaned


def tag_path(value: str) -> str:
    """Return a normalized tag path, refusing what the taxonomy cannot hold.

    The server normalizes the path the same way, so this only spares a round
    trip: empty segments, blank segments, control characters, and a path or a
    segment longer than the taxonomy accepts are refused here.
    """
    display = text(value, field="tag path", max_length=MAX_TAG_PATH_CHARS)
    segments = [segment.strip() for segment in display.split("/")]
    if any(not segment for segment in segments):
        raise UsageError("tag path cannot contain an empty segment")
    for segment in segments:
        if len(segment) > MAX_TAG_SEGMENT_CHARS:
            raise UsageError(f"tag path segment {segment!r} is longer than {MAX_TAG_SEGMENT_CHARS} characters")
        _reject_control(segment, field="tag path", allow_newlines=False)
    return "/".join(segments)


def identifier(value: str, *, field: str) -> str:
    """Return one artifact or tag id, refusing what could not name a stored row."""
    cleaned = value.strip()
    if not cleaned:
        raise UsageError(f"{field} cannot be blank")
    if len(cleaned) > MAX_IDENTIFIER_CHARS:
        raise UsageError(f"{field} is longer than {MAX_IDENTIFIER_CHARS} characters")
    if "/" in cleaned or any(character.isspace() for character in cleaned):
        raise UsageError(f"{field} cannot contain whitespace or '/'")
    _reject_control(cleaned, field=field, allow_newlines=False)
    return cleaned


def query(value: str | None) -> str | None:
    """Return one search query, refusing control characters and absurd lengths."""
    if value is None:
        return None
    return text(value, field="--query", max_length=MAX_QUERY_CHARS)


def metadata(pairs: Iterable[str], source: str) -> dict[str, str]:
    """Turn repeated ``KEY=VALUE`` flags plus ``--source`` into one checked mapping.

    Keys are plain tokens because they end up as JSON object keys in a stored
    row, values are single-line and bounded so metadata cannot become a second,
    unchecked payload, and a repeated key is refused instead of silently
    letting the last one win.
    """
    entries: dict[str, str] = {}
    for pair in pairs:
        key, separator, value = pair.partition("=")
        key = key.strip()
        if not separator or not key:
            raise UsageError(f"--metadata expects KEY=VALUE, got {pair!r}")
        if key == "source":
            raise UsageError("source is set by --source, not --metadata")
        if len(key) > MAX_METADATA_KEY_CHARS or not all(character.isalnum() or character in "_.-" for character in key):
            raise UsageError(f"metadata key {key!r} must be a plain token of letters, digits, '_', '.', or '-'")
        if key in entries:
            raise UsageError(f"metadata key {key!r} was given twice")
        entries[key] = text(value, field=f"--metadata {key}", max_length=MAX_METADATA_VALUE_CHARS)
    trimmed = text(source, field="--source", max_length=MAX_METADATA_VALUE_CHARS)
    entries["source"] = trimmed
    serialized = json.dumps(entries, ensure_ascii=False, separators=(",", ":"))
    if len(serialized) > MAX_METADATA_TOTAL_CHARS:
        raise UsageError(f"metadata is longer than {MAX_METADATA_TOTAL_CHARS} characters")
    return entries


def read_text(source: str | None, *, field: str, max_length: int, allow_newlines: bool = False) -> str:
    """Read a field from a file or standard input, stopping one character past its limit.

    The read is bounded, so a pipe that never ends, a mistake like
    ``--body-file /dev/zero``, or a gigabyte file fails at the boundary instead
    of allocating the whole stream and posting it.
    """
    if source is None:
        raise UsageError(f"{field} needs a file path or - for standard input")
    stream = sys.stdin
    close = False
    if source != "-":
        try:
            stream = open(source, encoding="utf-8")
            close = True
        except OSError as error:
            raise UsageError(f"could not read {source}: {error.strerror or error}") from error
    try:
        value = stream.read(max_length + 1)
    except (OSError, UnicodeDecodeError) as error:
        raise UsageError(f"could not read {source}: {error}") from error
    finally:
        if close:
            stream.close()
    return text(value, field=field, max_length=max_length, allow_newlines=allow_newlines)


def json_object(text_value: str, *, field: str, allowed: frozenset[str]) -> dict[str, Any]:
    """Parse one JSON object and refuse any key the stored model would drop.

    Pydantic ignores an unknown field by default, so a typo in typed content
    would silently store less than the caller wrote. Naming the allowed keys
    turns that into a usage error the shell can act on.
    """
    try:
        payload = json.loads(text_value)
    except ValueError as error:
        raise UsageError(f"{field} is not valid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise UsageError(f"{field} must be a JSON object")
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise UsageError(f"{field} has unknown keys: {', '.join(unknown)}; allowed: {', '.join(sorted(allowed))}")
    return payload


def _reject_control(value: str, *, field: str, allow_newlines: bool) -> None:
    """Refuse control characters, which a stored row and a log line cannot carry."""
    allowed = _BODY_FIELDS_ALLOWED if allow_newlines else _LINE_FIELDS_ALLOWED
    for character in value:
        if character in allowed or unicodedata.category(character) != "Cc":
            continue
        raise UsageError(f"{field} cannot contain control characters")
