"""Persist the files that arrived with one conversation turn.

The browser submits pasted images as base64 data URLs inside the user message,
so the model receives pixels but no file it can hand to ``view_image``, LaTeX, or
a shell command. This service writes those same bytes below the owning session's
directory when the message is submitted, which is the location the session-files
system message names for the model.

The user message itself is unchanged: the immutable raw message keeps carrying
the data URL. Channel attachments are the same idea for inbound IM media: the
plugin already holds the bytes, and these files are the model-facing handle on
them.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from mimetypes import guess_extension
from pathlib import Path

from ..._compat import UTC
from ...infra.files.object_store import get_object_store
from ...infra.log import get_logger
from ...messages import FrontUserMessage, MessagePartCodec
from ..files.object_store import session_directory_key, session_upload_key

logger = get_logger(__name__)

_CODEC = MessagePartCodec()
_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
_SAFE_SUFFIX = re.compile(r"\.[a-z0-9]{1,16}")
_MAX_NAME_LENGTH = 64


@dataclass(frozen=True, slots=True)
class SessionFileWrite:
    """One file to persist below a session directory."""

    name: str
    mime_type: str
    data: bytes


@dataclass(frozen=True, slots=True)
class StoredSessionFile:
    """One written file below the session directory."""

    #: Filename the sender or browser submitted.
    name: str
    #: MIME type the payload was submitted with.
    mime_type: str
    #: Relative ObjectKey that resolves below ``settings.storage_root``.
    object_key: str
    size_bytes: int
    sha256: str


def _upload_suffix(name: str, mime_type: str) -> str:
    """Prefer the submitted extension, then the one its MIME type names.

    Pasted screenshots arrive named ``Pasted image`` without an extension, and a
    suffixless file is awkward for LaTeX and shell tools that key off one.
    """
    suffix = Path(name).suffix.lower()
    if _SAFE_SUFFIX.fullmatch(suffix):
        return suffix
    guessed = (guess_extension(mime_type, strict=False) or "").lower()
    return guessed if _SAFE_SUFFIX.fullmatch(guessed) else ""


def _upload_name(moment: datetime, position: int, name: str, mime_type: str) -> str:
    """Compose one sortable, filesystem-safe upload name from a submitted part.

    The UTC stamp orders uploads chronologically so the newest files of a
    conversation are identifiable without extra metadata, and the position keeps
    several images of one message in the order the browser sent them.
    """
    suffix = _upload_suffix(name, mime_type)
    # Drop the submitted extension before sanitizing so the resolved suffix is
    # appended exactly once.
    base = name[: len(name) - len(suffix)] if suffix and name.lower().endswith(suffix) else name
    stem = _UNSAFE_NAME.sub("-", base).strip("-.")[:_MAX_NAME_LENGTH]
    stamp = moment.strftime("%Y%m%dT%H%M%S%fZ")
    return f"{stamp}-{position}-{stem}{suffix}" if stem else f"{stamp}-{position}{suffix}"


async def store_session_files(
    session_id: str,
    files: Sequence[SessionFileWrite],
) -> list[StoredSessionFile | None]:
    """Write each file below its session directory, keeping the input order.

    One unwritable file is ``None`` at its own position: media that arrives over
    a channel is already part of the conversation, so a storage failure must
    degrade that attachment instead of dropping the whole turn.
    """
    object_store = get_object_store()
    moment = datetime.now(UTC)
    stored: list[StoredSessionFile | None] = []
    for position, item in enumerate(files, start=1):
        key = session_upload_key(session_id, _upload_name(moment, position, item.name, item.mime_type))
        try:
            written = await object_store.write(key, item.data)
        except Exception:
            logger.exception("Could not store a session file; session_id=%s name=%r", session_id, item.name)
            stored.append(None)
            continue
        stored.append(
            StoredSessionFile(
                name=item.name,
                mime_type=item.mime_type,
                object_key=str(written.key),
                size_bytes=written.size_bytes,
                sha256=written.sha256,
            )
        )
    return stored


async def store_message_images(session_id: str, message: FrontUserMessage) -> list[StoredSessionFile | None]:
    """Write every base64 image of one submitted turn below its session directory.

    Images submitted as remote http(s) URLs are skipped: nothing local exists to
    store for them, and the model can already read the URL itself.

    Example:
        ``await store_message_images("session-1", payload)`` returns one entry
        per stored file, such as
        ``assets/sessions/session-1/uploads/20260920T144512123456Z-1-clipboard.png``.
    """
    images = _CODEC.decode_images(message)
    return await store_session_files(
        session_id,
        [SessionFileWrite(name=image.name, mime_type=image.mime_type, data=image.data) for image in images],
    )


async def delete_session_files(session_id: str) -> int:
    """Remove every file a deleted conversation owned below its session directory.

    Uploaded message images have no metadata row, so the session directory is
    deleted whole rather than file by file. The directory holds only
    session-owned objects: session assets and message uploads.
    """
    return await get_object_store().delete_tree(session_directory_key(session_id))


__all__ = [
    "SessionFileWrite",
    "StoredSessionFile",
    "delete_session_files",
    "store_message_images",
    "store_session_files",
]
