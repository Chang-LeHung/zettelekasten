"""Persist one page capture below the conversation that asked for it.

A screenshot is an image, so it cannot travel back through the bounded JSON tool
result: the model would receive megabytes of base64 it cannot read. The panel
sends the JPEG once, this service writes it into the session's upload
directory — the location the session-files system message already names — and
the tool answers with a path the model can hand to ``read``.
"""

from dataclasses import dataclass

from zett.application.files.object_store import ObjectKey
from zett.infra.files.object_store import get_object_store

from ..assets.message_files import SessionFileWrite, store_session_files
from .browser import BrowserResult


@dataclass(frozen=True, slots=True)
class StoredScreenshot:
    """One capture on disk, described by what the model needs to open it."""

    #: Absolute path the filesystem tools accept.
    path: str
    #: Canonical object key below the storage root.
    key: str
    size_bytes: int


async def store_browser_screenshot(session_id: str, result: BrowserResult) -> StoredScreenshot:
    """Write one captured JPEG below ``assets/sessions/<session>/uploads/``.

    The bytes are validated by the transport model (JPEG signature, base64,
    size), so a page can never make this write anything else.
    """
    data = result.screenshot_bytes()
    [stored] = await store_session_files(
        session_id,
        [SessionFileWrite(name="screenshot.jpg", mime_type="image/jpeg", data=data)],
    )
    if stored is None:
        raise ValueError("The capture could not be written to the session directory")
    path = get_object_store().resolve(ObjectKey(stored.object_key))
    return StoredScreenshot(path=str(path), key=stored.object_key, size_bytes=stored.size_bytes)
