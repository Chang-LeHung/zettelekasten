"""Persist one page capture below the conversation that asked for it.

A screenshot is an image, so it cannot travel back through the bounded JSON tool
result: the model would receive megabytes of base64 it cannot read. The panel
sends the JPEG once, this service writes it into the session's upload directory —
the location the session-files system message already names — and the tool
answers with a path the model can hand to ``read``.

One conversation keeps one capture file: each new screenshot replaces the last,
so an investigation that captures repeatedly cannot leave hundreds of megabytes
behind, and the path the model was given stays the file it just asked for.
"""

from dataclasses import dataclass

from zett.application.files.object_store import session_upload_key
from zett.infra.files.object_store import get_object_store

from .browser import BrowserResult

#: The one file name a session's capture uses, so a new capture replaces it.
SCREENSHOT_NAME = "screenshot.jpg"


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
    store = get_object_store()
    written = await store.write(session_upload_key(session_id, SCREENSHOT_NAME), data)
    return StoredScreenshot(
        path=str(store.resolve(written.key)),
        key=str(written.key),
        size_bytes=written.size_bytes,
    )
