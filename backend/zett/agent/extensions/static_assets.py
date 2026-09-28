"""Publish a file into the global Static Assets library, and say what it is for."""

import mimetypes
from pathlib import Path

from zett_agent.agent import (
    AgentRunContext,
)
from zett_agent.extensions.base import (
    AgentExtension,
)
from zett_agent.messages import (
    SystemMessage,
)
from zett_agent.tools.base import (
    tool,
)

from ...application.assets.asset_views import StaticAssetReceipt, static_asset_receipt
from ...application.assets.static_assets import static_asset_service


class StaticAssetExtension(AgentExtension):
    """Own the library of files that must outlive a conversation.

    Publishing never moves a whole binary through the model context: the model
    writes or compiles the file on disk and hands ``upload_static_asset`` its
    path, and the tool reads the file server-side. The same endpoint stays
    reachable over HTTP for a script or a shell, which is why the route is the
    boundary rather than the tool.

    The message states what the library is for, never a snapshot of it, so it is
    byte-identical on every turn of one session and extends the leading system
    prefix instead of invalidating the provider prompt cache.
    """

    async def on_tool(self, context: AgentRunContext) -> None:
        """Register the publish tool bound to the configured size limit."""
        max_bytes = await static_asset_service.max_upload_size()

        @tool
        async def upload_static_asset(
            path: str,
            name: str | None = None,
            mime_type: str | None = None,
        ) -> StaticAssetReceipt:
            """Publish a file into the global Static Assets library.

            Args:
                path: Absolute path of the file to publish.
                name: User-facing name; defaults to the file's own name.
                mime_type: IANA media type; guessed from the file name when omitted.

            Snippet:
                upload_static_asset(path="/tmp/paper.pdf")

            Guidelines:
                - Publish a file that must outlive this conversation; material only this conversation needs belongs in a session asset.
                - Write or download the file first and pass its absolute path: bytes never travel through an argument.
                - Files above the configured asset size limit are refused before anything is stored.
                - The answer carries the id `set_asset_tags` takes and the URL this site serves the file from.
            """
            file_name, payload, guessed = _read_publish(
                path,
                name=name,
                mime_type=mime_type,
                max_bytes=max_bytes,
            )
            stored = await static_asset_service.upload(name=file_name, mime_type=guessed, content=payload)
            return static_asset_receipt(stored)

        context.register_tool(upload_static_asset)

    async def on_state(self, context: AgentRunContext) -> None:
        """Place the upload instructions after existing system instructions."""
        message = SystemMessage(content=self._instructions())
        instructions = [item for item in context.state.messages if isinstance(item, SystemMessage)]
        context.add_message(message, index=len(instructions))

    def _instructions(self) -> str:
        """Say what belongs in the library and which tools work on it."""
        return (
            "# Static assets\n"
            "Files that must outlive this conversation belong to the global Static Assets library, which every "
            "conversation and the Library view share.\n"
            "Publish one with `upload_static_asset`, naming a file you already wrote by its absolute path, and classify "
            "it with `create_asset_tag`, `list_asset_tags`, and `set_asset_tags`, which work on the file library's own "
            "collection tree. Keep material that only this conversation needs in its own session assets."
        )


def _read_publish(
    source: str,
    *,
    name: str | None,
    mime_type: str | None,
    max_bytes: int,
) -> tuple[str, bytes, str | None]:
    """Read one file to publish as (name, bytes, media type).

    The path must be absolute, the way the shell tools name files: a relative
    path would mean the server process' working directory rather than the one the
    model wrote into. There is no directory boundary here — the whole point is to
    publish a file the model produced — but the size limit is enforced before the
    bytes are read, so an oversized file never fills memory first.
    """
    candidate = Path(source)
    if not candidate.is_absolute():
        raise ValueError(f"Publish path must be absolute: {source}")
    resolved = candidate.resolve()
    if not resolved.is_file():
        raise ValueError(f"File not found: {source}")
    size = resolved.stat().st_size
    if size > max_bytes:
        raise ValueError(f"File is {size} bytes; the asset limit is {max_bytes}")
    file_name = (name or resolved.name).strip()
    if not file_name:
        raise ValueError("Asset name cannot be blank")
    guessed = mime_type or mimetypes.guess_type(file_name)[0]
    return file_name, resolved.read_bytes(), guessed


__all__ = ["StaticAssetExtension"]
