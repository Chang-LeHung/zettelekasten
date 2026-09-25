"""Tell the model how to publish a file into the global Static Assets library."""

from zett_agent import AgentExtension, AgentRunContext, SystemMessage

from ...config import settings

#: Hosts that only describe a listening socket, never a dialable address.
_WILDCARD_HOSTS = {"0.0.0.0", "::", "[::]"}


class StaticAssetExtension(AgentExtension):
    """Name the local upload endpoint for files that must outlive a conversation.

    Publishing is an HTTP call instead of a tool argument: the model already
    writes and compiles files on disk, so uploading those bytes with a shell
    command never moves a whole binary through the model context as Base64.

    The message names an endpoint and its contract, never a snapshot of the
    library, so it is byte-identical on every turn of one session and extends
    the leading system prefix instead of invalidating the provider prompt cache.
    """

    async def on_state(self, context: AgentRunContext) -> None:
        """Place the upload instructions after existing system instructions."""
        message = SystemMessage(content=self._instructions())
        instructions = [item for item in context.state.messages if isinstance(item, SystemMessage)]
        context.add_message(message, index=len(instructions))

    def _instructions(self) -> str:
        """Describe the upload endpoint in the terms a shell command needs."""
        base_url = f"http://{_dialable_host()}:{settings.port}"
        return (
            "# Static assets\n"
            f"Files that must outlive this conversation belong to the global Static Assets library at {base_url}/api/assets.\n"
            "Publish one by uploading bytes you already wrote, without sending them through the conversation:\n"
            f'curl -sS -X POST "{base_url}/api/assets/upload?name=paper.pdf" '
            '-H "Content-Type: application/pdf" --data-binary @/absolute/path/to/paper.pdf\n'
            f"List the library with `curl -sS {base_url}/api/assets`; the upload response carries the stored id, name, "
            "content_url, and size_bytes. Keep material that only this conversation needs in its own session assets."
        )


def _dialable_host() -> str:
    """Return a host a shell command can reach, replacing a wildcard bind address."""
    return "127.0.0.1" if settings.host in _WILDCARD_HOSTS else settings.host


__all__ = ["StaticAssetExtension"]
