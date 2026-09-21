"""Persist the images submitted with one conversation turn.

The browser submits pasted images as base64 data URLs inside the user message,
so the model receives pixels but no file it can hand to ``view_image``, LaTeX, or
a shell command. This service writes those same bytes below the owning session's
directory when the message is submitted, which is the location the session-files
system message names for the model.

The user message itself is unchanged: the immutable raw message keeps carrying
the data URL, and these files are the model-facing handle for the same bytes.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from mimetypes import guess_extension
from pathlib import Path

from ...infra.files.object_store import get_object_store
from ...messages import FrontUserMessage, MessagePartCodec
from ..files.object_store import session_directory_key, session_upload_key

_CODEC = MessagePartCodec()
_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
_SAFE_SUFFIX = re.compile(r"\.[a-z0-9]{1,16}")
_MAX_NAME_LENGTH = 64


@dataclass(frozen=True, slots=True)
class StoredMessageImage:
    """One submitted image that now exists as a file below the session directory."""

    #: Name the browser submitted with the image part.
    name: str
    #: MIME type carried by the source data URL.
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


async def store_message_images(session_id: str, message: FrontUserMessage) -> list[StoredMessageImage]:
    """Write every base64 image of one submitted turn below its session directory.

    Images submitted as remote http(s) URLs are skipped: nothing local exists to
    store for them, and the model can already read the URL itself.

    Example:
        ``await store_message_images("session-1", payload)`` returns one entry
        per stored file, such as
        ``assets/sessions/session-1/uploads/20260920T144512123456Z-1-clipboard.png``.
    """
    images = _CODEC.decode_images(message)
    object_store = get_object_store()
    moment = datetime.now(UTC)
    stored: list[StoredMessageImage] = []
    for position, image in enumerate(images, start=1):
        key = session_upload_key(session_id, _upload_name(moment, position, image.name, image.mime_type))
        written = await object_store.write(key, image.data)
        stored.append(
            StoredMessageImage(
                name=image.name,
                mime_type=image.mime_type,
                object_key=str(written.key),
                size_bytes=written.size_bytes,
                sha256=written.sha256,
            )
        )
    return stored


async def delete_session_files(session_id: str) -> int:
    """Remove every file a deleted conversation owned below its session directory.

    Uploaded message images have no metadata row, so the session directory is
    deleted whole rather than file by file. The directory holds only
    session-owned objects: session assets and message uploads.
    """
    return await get_object_store().delete_tree(session_directory_key(session_id))


__all__ = ["StoredMessageImage", "delete_session_files", "store_message_images"]
